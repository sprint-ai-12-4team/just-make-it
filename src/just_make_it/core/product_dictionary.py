"""품목 사전: 텍스트 모델이나 klein이 잘 모르는 한국 품목의 생김새 묘사.

- description: 이미지 프롬프트에 그대로 넣을 영어 생김새 묘사 (사람이 작성)
- local_ok: klein이 이 묘사만으로 제대로 그리는지. False면 참고 사진이 없을 때 처음부터 flare로 만듦
"""

PRODUCT_DICTIONARY = {
    "소금빵": {
        "description": (
            "glossy golden-brown butter roll with a rolled spiral shape, coarse sea salt flakes on top, "
            "flat crispy caramelized bottom where butter melted out"
        ),
        "local_ok": False,
    },
}


def lookup(product_name):
    """상품 이름으로 품목 사전을 찾습니다. 띄어쓰기는 무시합니다.

    Args:
        product_name: 가게 또는 상품 이름

    Returns:
        dict 또는 None: 사전에 있으면 {"description", "local_ok"}, 없으면 None
    """
    key = product_name.replace(" ", "")
    for name, entry in PRODUCT_DICTIONARY.items():
        if name.replace(" ", "") == key:
            return entry
    return None
