"""FLUX.2 klein fp8 본체 파일을 diffusers 모델로 불러옵니다.

BFL fp8 파일은 가중치를 8비트로 줄여 저장하고, 원래 크기로 되돌리는 스케일 값을 따로 담고 있습니다.
diffusers는 이 형식을 바로 읽지 못해서, 아래 순서로 직접 불러옵니다.

1. 스케일 값을 곱해 원래 가중치로 되돌린 뒤 diffusers 모델을 만듦 (CPU에서 잠깐 원본 크기만큼 메모리를 씀)
2. 8비트로 저장된 층은 다시 8비트 가중치와 스케일 값만 들고 있는 층(Fp8Linear)으로 바꿈
3. 계산할 때만 그 층의 가중치를 원래 크기로 되돌려서 씀

torch와 diffusers가 있는 GPU 서버에서만 불러오는 파일입니다.
"""

import torch
import torch.nn.functional as F
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
        ValueError: 스케일 값이 붙은 가중치가 8비트 2차원이 아니거나, 모델 크기와 다를 때
    """
    state = {k.removeprefix(PREFIX): v for k, v in load_file(checkpoint).items()}
    scales = split_scales(state)

    fp8_layers = {}
    restored = {}
    for key, value in state.items():
        scale = scales.get(key)
        if scale is None and value.dtype == torch.float8_e4m3fn:
            scale = torch.tensor(1.0)
        if scale is None:
            restored[key] = value
            continue
        if value.dtype != torch.float8_e4m3fn or value.ndim != 2:
            raise ValueError(
                f"{key}는 스케일 값이 있는데 8비트 2차원 가중치가 아닙니다."
            )
        row_scale = scale.float().reshape(-1, 1) if scale.numel() > 1 else scale.float()
        restored[key] = (value.float() * row_scale).to(torch.bfloat16)

        # diffusers 이름으로 바꿀 때 qkv처럼 한 가중치가 여러 개로 나뉘기도 해서, 같은 변환을 스케일에도 적용
        pieces = convert_flux2_transformer_checkpoint_to_diffusers({key: value})
        if scale.numel() > 1:
            piece_scales = convert_flux2_transformer_checkpoint_to_diffusers(
                {key: scale}
            )
        else:
            piece_scales = dict.fromkeys(pieces, scale)
        for new_key, piece in pieces.items():
            fp8_layers[new_key] = (piece, piece_scales[new_key])
    del state

    transformer = Flux2Transformer2DModel.from_single_file(
        restored,
        config=config_repo,
        subfolder="transformer",
        torch_dtype=torch.bfloat16,
    )
    del restored

    for new_key, (weight, scale) in fp8_layers.items():
        parent_name, _, name = new_key.removesuffix(".weight").rpartition(".")
        parent = transformer.get_submodule(parent_name)
        old = getattr(parent, name)
        if tuple(old.weight.shape) != tuple(weight.shape):
            raise ValueError(f"{new_key} 크기가 모델과 다릅니다.")
        setattr(parent, name, Fp8Linear(weight, scale, old.bias))
    return transformer
