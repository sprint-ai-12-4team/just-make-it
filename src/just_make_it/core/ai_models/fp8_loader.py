"""FLUX.2 klein fp8 본체 파일을 diffusers 모델로 불러옵니다.

BFL fp8 파일은 가중치를 8비트로 줄여 저장하고, 원래 크기로 되돌리는 스케일 값을 따로 담고 있습니다.
diffusers는 이 형식을 바로 읽지 못해서, 아래 순서로 직접 불러옵니다.

1. 빈 모델 틀만 만듦 (메모리를 거의 안 씀)
2. 파일의 가중치를 하나씩 diffusers 이름으로 바꿔 틀에 채움
   - 8비트 층은 원래 크기로 되돌리지 않고, 8비트 가중치와 스케일 값만 들고 있는 층(Fp8Linear)으로 끼움
   - 나머지(정규화, 편향 등)는 bf16으로 채움
3. 계산할 때만 8비트 층의 가중치를 원래 크기로 되돌려서 씀

배포 VM의 시스템 메모리가 16GB라서, 원래 크기 가중치를 한꺼번에 만들지 않고 파일 크기(약 4GB) 정도만 쓰게 했습니다.
torch와 diffusers가 있는 GPU 서버에서만 불러오는 파일입니다.
"""

import torch
import torch.nn.functional as F
from accelerate import init_empty_weights
from accelerate.utils import set_module_tensor_to_device
from diffusers import Flux2Transformer2DModel
from diffusers.loaders.single_file_utils import (
    convert_flux2_transformer_checkpoint_to_diffusers,
)
from safetensors.torch import load_file
from torch import nn

WEIGHT_SCALE_SUFFIXES = (".weight_scale", ".scale_weight")
INPUT_SCALE_SUFFIXES = (".input_scale", ".scale_input")
PREFIX = "model.diffusion_model."


class Fp8Linear(nn.Module):
    """8비트 가중치와 스케일 값만 들고 있다가, 계산할 때만 원래 가중치로 되돌리는 층.

    가중치를 파라미터가 아니라 버퍼로 두는 이유: diffusers는 첫 번째 파라미터의 자료형을 모델 자료형으로 보고
    입력을 그 자료형으로 바꾸는데, 8비트 가중치가 파라미터면 입력까지 8비트로 바뀌어 버립니다.
    """

    def __init__(self, weight, scale, bias=None):
        super().__init__()
        self.out_features, self.in_features = weight.shape
        self.register_buffer("weight", weight.contiguous())
        scale = scale.float()
        self.register_buffer(
            "scale", scale.reshape(-1, 1) if scale.numel() > 1 else scale.reshape(())
        )
        self.bias = bias

    def forward(self, x):
        weight = (self.weight.float() * self.scale).to(x.dtype)
        return F.linear(x, weight, self.bias)


def split_scales(state):
    """파일에서 스케일 값을 꺼내 가중치 이름별로 모읍니다. 입력 스케일은 쓰지 않아서 버립니다.

    Returns:
        dict: 가중치 이름별 스케일 값
    """
    scales = {}
    for key in list(state):
        if key.endswith(WEIGHT_SCALE_SUFFIXES):
            suffix = next(s for s in WEIGHT_SCALE_SUFFIXES if key.endswith(s))
            scales[key[: -len(suffix)] + ".weight"] = state.pop(key)
        elif key.endswith(INPUT_SCALE_SUFFIXES):
            state.pop(key)
    return scales


def load_fp8_transformer(checkpoint, config_repo):
    """fp8 본체 파일을 불러옵니다.

    Args:
        checkpoint: fp8 safetensors 파일 경로
        config_repo: 설정을 가져올 원본 저장소 (transformer 폴더의 config.json 사용)

    Returns:
        Flux2Transformer2DModel: 8비트 층이 Fp8Linear로 바뀐 모델

    Raises:
        ValueError: 스케일 값이 붙은 가중치가 8비트 2차원이 아니거나, 파일과 모델이 맞지 않을 때
    """
    config = Flux2Transformer2DModel.load_config(config_repo, subfolder="transformer")
    with init_empty_weights():
        transformer = Flux2Transformer2DModel.from_config(config).to(torch.bfloat16)

    state = {k.removeprefix(PREFIX): v for k, v in load_file(checkpoint).items()}
    scales = split_scales(state)
    for key in list(state):
        value = state.pop(key)
        scale = scales.get(key)
        if scale is None and value.dtype == torch.float8_e4m3fn:
            scale = torch.tensor(1.0)
        # diffusers 이름으로 바꿀 때 qkv처럼 한 가중치가 여러 개로 나뉘기도 함
        pieces = convert_flux2_transformer_checkpoint_to_diffusers({key: value})
        if scale is None:
            for new_key, piece in pieces.items():
                if piece.is_floating_point():
                    piece = piece.to(torch.bfloat16)
                set_module_tensor_to_device(
                    transformer, new_key, "cpu", value=piece, dtype=piece.dtype
                )
            continue

        if value.dtype != torch.float8_e4m3fn or value.ndim != 2:
            raise ValueError(
                f"{key}는 스케일 값이 있는데 8비트 2차원 가중치가 아닙니다."
            )
        # 줄마다 스케일 값이 있으면 가중치와 똑같이 나눠야 해서 같은 변환을 적용
        if scale.numel() > 1:
            piece_scales = convert_flux2_transformer_checkpoint_to_diffusers(
                {key: scale}
            )
        else:
            piece_scales = dict.fromkeys(pieces, scale)
        for new_key, piece in pieces.items():
            _swap_in_fp8(transformer, new_key, piece, piece_scales[new_key])

    empty = [
        name
        for name, tensor in [
            *transformer.named_parameters(),
            *transformer.named_buffers(),
        ]
        if tensor.device.type == "meta"
    ]
    if empty:
        raise ValueError(f"파일에 없는 가중치가 있습니다. 예: {empty[0]}")
    return transformer.eval()


def _swap_in_fp8(transformer, weight_key, weight, scale):
    """빈 모델 틀의 Linear 층을 Fp8Linear로 바꿔 끼웁니다. 편향은 나중에 따로 채워짐."""
    parent_name, _, name = weight_key.removesuffix(".weight").rpartition(".")
    parent = transformer.get_submodule(parent_name)
    old = getattr(parent, name)
    if tuple(old.weight.shape) != tuple(weight.shape):
        raise ValueError(f"{weight_key} 크기가 모델과 다릅니다.")
    setattr(parent, name, Fp8Linear(weight.contiguous(), scale, old.bias))
