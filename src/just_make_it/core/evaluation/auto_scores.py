"""정량평가용 자동 점수 (M1~M3). 평가 때만 CPU로 채점 모델을 띄우고, 서빙에는 넣지 않습니다.

- clip_score: 영어 묘사와 글자 없는 그림이 얼마나 맞는지 (CLIP 글-그림 코사인 유사도)
- ref_similarity: 참고 사진과 글자 없는 그림이 얼마나 닮았는지 (CLIP 그림-그림 코사인 유사도)
- ocr_match: 얹은 문구를 OCR로 다시 읽었을 때 맞은 글자 비율 (combined만)

점수는 높을수록 좋습니다. CLIP 유사도는 보통 0.2~0.35 사이라, 같은 케이스끼리 실행을 비교할 때 씁니다.
채점 모델은 eval 묶음 패키지가 필요합니다: uv sync --extra eval
"""

import io
import re
from difflib import SequenceMatcher

from PIL import Image

CLIP_MODEL = "openai/clip-vit-base-patch32"
OCR_LANGS = ["ko", "en"]

# 프롬프트에서 그림 내용이 아닌 지시문은 빼고 CLIP에 넣음 ("No text" 같은 부정문은 CLIP이 이해하지 못함)
_PROMPT_NOISE = (
    "Use the product",
    "Keep the",
    "Only change",
    "Props and",
    "The lower center",
    "No ",
    "Photorealistic",
    "Mood:",
)


def clip_text(prompt):
    """이미지 프롬프트에서 상품과 장면 묘사 문장만 남깁니다.

    Args:
        prompt: 실제로 쓴 영어 이미지 프롬프트

    Returns:
        str: CLIP에 넣을 묘사
    """
    sentences = re.split(r"(?<=\.)\s+", prompt.strip())
    kept = [s for s in sentences if s and not s.startswith(_PROMPT_NOISE)]
    return " ".join(kept)


def char_match(target, read):
    """목표 문구 중 OCR이 맞게 읽은 글자 비율. 띄어쓰기와 문장부호는 빼고 비교합니다.

    Args:
        target: 이미지에 얹은 문구
        read: OCR이 읽은 글

    Returns:
        float: 0~1, 목표 문구가 비었으면 None
    """
    target = _letters(target)
    read = _letters(read)
    if not target:
        return None
    matched = sum(
        b.size for b in SequenceMatcher(None, target, read).get_matching_blocks()
    )
    return round(matched / len(target), 4)


def _letters(text):
    return re.sub(r"[\s\W_]+", "", text or "")


class Scorer:
    """CLIP과 OCR을 처음 쓸 때 한 번만 CPU로 불러와 재사용합니다."""

    def __init__(self):
        self._clip = None
        self._ocr = None

    def _load_clip(self):
        if self._clip is None:
            try:
                import torch
                from transformers import CLIPModel, CLIPProcessor
            except ImportError as e:
                raise RuntimeError(
                    "CLIP 채점에는 eval 패키지가 필요합니다: uv sync --extra eval"
                ) from e
            model = CLIPModel.from_pretrained(CLIP_MODEL).eval()
            self._clip = (torch, model, CLIPProcessor.from_pretrained(CLIP_MODEL))
        return self._clip

    def _image_features(self, image_bytes):
        torch, model, processor = self._load_clip()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        with torch.no_grad():
            inputs = processor(images=image, return_tensors="pt")
            features = model.get_image_features(**inputs)
        return features / features.norm(dim=-1, keepdim=True)

    def clip_score(self, image_bytes, prompt):
        """영어 묘사와 그림의 CLIP 코사인 유사도."""
        torch, model, processor = self._load_clip()
        text = clip_text(prompt)
        if not text:
            return None
        with torch.no_grad():
            inputs = processor(
                text=[text], return_tensors="pt", padding=True, truncation=True
            )
            text_features = model.get_text_features(**inputs)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        image_features = self._image_features(image_bytes)
        return round(float((image_features @ text_features.T).item()), 4)

    def ref_similarity(self, image_bytes, reference_bytes):
        """참고 사진과 그림의 CLIP 코사인 유사도."""
        a = self._image_features(image_bytes)
        b = self._image_features(reference_bytes)
        return round(float((a @ b.T).item()), 4)

    def ocr_text(self, image_bytes):
        """이미지에 있는 글자를 읽습니다."""
        if self._ocr is None:
            try:
                import easyocr
            except ImportError as e:
                raise RuntimeError(
                    "OCR 채점에는 eval 패키지가 필요합니다: uv sync --extra eval"
                ) from e
            self._ocr = easyocr.Reader(OCR_LANGS, gpu=False, verbose=False)
        import numpy as np

        image = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        return " ".join(self._ocr.readtext(image, detail=0))

    def ocr_match(self, image_bytes, text):
        """얹은 문구를 다시 읽어 맞은 글자 비율."""
        return char_match(text, self.ocr_text(image_bytes))


def score_row(scorer, row, image_bytes, background_bytes, reference_bytes=None):
    """한 케이스의 자동 점수를 계산합니다. 실패하거나 해당 없는 칸은 빈 문자열입니다.

    Args:
        scorer: Scorer
        row: results.csv 한 줄 (output, prompt, overlay_text 사용)
        image_bytes: 최종 이미지 (combined면 문구를 얹은 이미지)
        background_bytes: 글자 없는 그림. 없으면 None (output=text)
        reference_bytes: 참고 사진. 없으면 None

    Returns:
        dict: clip_score, ref_similarity, ocr_match
    """
    scores = {"clip_score": "", "ref_similarity": "", "ocr_match": ""}
    if background_bytes and row.get("prompt"):
        scores["clip_score"] = _or_blank(
            scorer.clip_score(background_bytes, row["prompt"])
        )
    if background_bytes and reference_bytes:
        scores["ref_similarity"] = _or_blank(
            scorer.ref_similarity(background_bytes, reference_bytes)
        )
    if row.get("output") == "combined" and image_bytes and row.get("overlay_text"):
        scores["ocr_match"] = _or_blank(
            scorer.ocr_match(image_bytes, row["overlay_text"])
        )
    return scores


def _or_blank(value):
    return "" if value is None else value
