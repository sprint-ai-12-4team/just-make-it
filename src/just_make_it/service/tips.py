"""대기 중 정보 카드 (GET /tips, api_spec_consult 2장). 1차 범위: 직접 쓴 카드만.

카드 내용은 프론트 기본 카드(frontend/lib/tips.ts)와 같게 시작했다. 바꿀 때는 이 파일만 고치면 되고,
서버 카드가 있으면 프론트는 이걸 쓴다.
- season(시즌 달력)·howto(후가공 요령): 직접 작성
- platform(플랫폼 제한)·law(광고 관련 법): 사람이 정리. checked_at = 마지막으로 확인한 날.
  공식 도움말 주소를 확인하면 source에 넣기 (지금은 비어 있음 → 프론트는 출처 없이 보여 줌)
- support(지원사업)·news(뉴스): 2차 (공공 API·검색 API를 하루 1번 받아 저장)

고르는 순서: 시즌(오늘부터 21일 안, 가까운 순) → 목적(purpose)·업종(category)이 맞는 카드 → 요령·법 번갈아
"""

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
SEASON_DAYS = 21
CHECKED = "2026-11-02"

# (id, kind, title, body, 조건). 조건: date(MM-DD, 시즌), purposes, categories, action
TIPS: list[dict] = [
    # 시즌
    {
        "id": "season-0214",
        "kind": "season",
        "date": "02-14",
        "title": "2월 14일 밸런타인데이",
        "body": "초콜릿·디저트·꽃 가게라면 일주일 전부터 올려 두세요.",
    },
    {
        "id": "season-0314",
        "kind": "season",
        "date": "03-14",
        "title": "3월 14일 화이트데이",
        "body": "사탕·선물 세트 광고는 10일 전쯤 올리면 미리 고르는 손님이 봐요.",
    },
    {
        "id": "season-0505",
        "kind": "season",
        "date": "05-05",
        "title": "5월 5일 어린이날",
        "body": "가족 손님이 많은 가게라면 '가족 세트'처럼 묶어서 알려 보세요.",
    },
    {
        "id": "season-0508",
        "kind": "season",
        "date": "05-08",
        "title": "5월 8일 어버이날",
        "body": "꽃·케이크·선물 가게는 예약을 미리 받는다고 함께 알리면 좋아요.",
    },
    {
        "id": "season-0515",
        "kind": "season",
        "date": "05-15",
        "title": "5월 15일 스승의 날",
        "body": "작은 선물·꽃 광고는 학부모가 보는 동네 채널에 올려 보세요.",
    },
    {
        "id": "season-1111",
        "kind": "season",
        "date": "11-11",
        "title": "11월 11일 빼빼로데이",
        "body": "과자·디저트 가게라면 일주일 전부터 '한정' 문구로 알려 보세요.",
        "action": {
            "label": "빼빼로데이 문구로 만들기",
            "href": "/create?message=%EB%B9%BC%EB%B9%BC%EB%A1%9C%EB%8D%B0%EC%9D%B4%20%ED%95%9C%EC%A0%95",
        },
    },
    {
        "id": "season-1225",
        "kind": "season",
        "date": "12-25",
        "title": "12월 25일 크리스마스",
        "body": "케이크·선물 예약은 2주 전부터 받는 가게가 많아요. 예약 마감일을 같이 적어 보세요.",
    },
    {
        "id": "season-1231",
        "kind": "season",
        "date": "12-31",
        "title": "한 해 마무리",
        "body": "'올해 감사했어요' 단골 인사 광고는 할인이 없어도 반응이 좋아요.",
    },
    # 후가공 요령 (결과 화면 기능으로 이어짐)
    {
        "id": "howto-cutout",
        "kind": "howto",
        "title": "상품만 남기고 배경 색 바꾸기",
        "body": "결과가 나오면 '배경 지우고 색 채우기'를 눌러 보세요. 흰 배경은 쇼핑몰에 잘 어울려요.",
    },
    {
        "id": "howto-text",
        "kind": "howto",
        "title": "글자가 상품을 가린다면",
        "body": "'글자 직접 고치기'에서 글자를 끌어 옮기거나 크기를 줄일 수 있어요.",
    },
    {
        "id": "howto-remake",
        "kind": "howto",
        "title": "마음에 안 들면 칩 하나만",
        "body": "'더 밝게', '배경 단순하게'를 골라 다시 만들면 처음보다 빨리 원하는 그림에 가까워져요.",
    },
    {
        "id": "howto-qr",
        "kind": "howto",
        "title": "그림에 가게 QR 넣기",
        "body": "결과 화면에서 가게 링크를 넣으면 QR을 그림 구석에 붙여 드려요. 전단지에 특히 좋아요.",
    },
    {
        "id": "howto-copy",
        "kind": "howto",
        "title": "같은 문구로 해시태그까지",
        "body": "결과 화면의 '다른 곳에 올릴 글로 바꾸기'에서 해시태그·블로그 제목을 바로 받아 보세요.",
    },
    # 플랫폼별
    {
        "id": "platform-ig-ratio",
        "kind": "platform",
        "purposes": ["instagram"],
        "title": "인스타 피드는 세로가 더 크게 보여요",
        "body": "정사각형도 괜찮지만, 세로형(4:5)이 화면을 더 많이 차지해요. 올리기 전에 미리보기로 잘리는 곳을 확인하세요.",
    },
    {
        "id": "platform-ig-grid",
        "kind": "platform",
        "purposes": ["instagram"],
        "title": "프로필 격자에서는 양옆이 잘려요",
        "body": "결과 화면의 '올리면 가려지는 곳 보기'로 중요한 글자가 잘리지 않는지 확인하세요.",
    },
    {
        "id": "platform-store-main",
        "kind": "platform",
        "purposes": ["commerce"],
        "title": "쇼핑몰 대표 이미지는 글자 없이",
        "body": "대표 이미지에 글자·워터마크를 넣으면 검색에 덜 나올 수 있어요. 올리기 전에 판매자 도움말을 확인하세요.",
        "action": {"label": "글자 없는 그림 저장", "href": "#save-background"},
    },
    {
        "id": "platform-store-white",
        "kind": "platform",
        "purposes": ["commerce"],
        "title": "대표 이미지는 깔끔한 배경이 유리해요",
        "body": "흰 배경을 권하는 쇼핑몰이 많아요. '배경 지우고 색 채우기'에서 흰색을 골라 보세요.",
    },
    {
        "id": "platform-yt-size",
        "kind": "platform",
        "purposes": ["youtube"],
        "title": "유튜브 썸네일은 2MB까지",
        "body": "파일이 크면 올라가지 않아요. 저장한 그림이 크다면 JPG로 바꿔 올려 보세요.",
    },
    {
        "id": "platform-yt-time",
        "kind": "platform",
        "purposes": ["youtube"],
        "title": "오른쪽 아래는 영상 길이에 가려요",
        "body": "중요한 글자는 가운데나 왼쪽에 두세요.",
    },
    {
        "id": "platform-kakao-ad",
        "kind": "platform",
        "purposes": ["kakao"],
        "title": "광고 메시지는 맨 앞에 (광고)",
        "body": "카톡·문자로 광고를 보낼 때는 '(광고)' 표시와 수신 거부 방법을 넣어야 해요. 밤 9시~아침 8시에는 따로 동의가 필요해요.",
    },
    # 법 (모든 곳 공통, "법률 자문이 아니에요"는 화면에서 붙임)
    {
        "id": "law-best",
        "kind": "law",
        "title": "'최고·1위'에는 근거가 필요해요",
        "body": "근거(출처·기준일) 없이 쓰면 표시광고법에 걸릴 수 있어요.",
    },
    {
        "id": "law-food",
        "kind": "law",
        "categories": ["cafe", "restaurant"],
        "title": "음식에 '병에 좋다'는 말은 조심",
        "body": "일반 식품에 질병 예방·치료 효과를 적으면 안 돼요.",
    },
    {
        "id": "law-discount",
        "kind": "law",
        "title": "할인 전 가격은 실제로 팔던 가격",
        "body": "올린 적 없는 가격에서 깎아 주는 것처럼 보이면 문제가 될 수 있어요.",
    },
    {
        "id": "law-face",
        "kind": "law",
        "title": "손님 얼굴·남의 로고는 빼 주세요",
        "body": "허락 없이 쓰면 초상권·상표권 문제가 생길 수 있어요.",
    },
]

CATEGORIES = ("cafe", "restaurant", "beauty", "flower", "fashion", "etc")


def days_until(mmdd: str, today: date) -> int:
    """오늘부터 그날까지 남은 날 (올해 지났으면 내년)."""
    month, day = (int(x) for x in mmdd.split("-"))
    target = date(today.year, month, day)
    if target < today:
        target = date(today.year + 1, month, day)
    return (target - today).days


def pick_tips(
    purpose: str | None = None,
    category: str | None = None,
    limit: int = 6,
    today: date | None = None,
) -> list[dict]:
    """보여 줄 카드 (API 응답 모양)."""
    today = today or datetime.now(KST).date()

    def fits(t: dict) -> bool:
        if t.get("purposes") and purpose not in t["purposes"]:
            return False
        return not (t.get("categories") and category not in t["categories"])

    season = sorted(
        (
            t
            for t in TIPS
            if t.get("date") and days_until(t["date"], today) <= SEASON_DAYS
        ),
        key=lambda t: days_until(t["date"], today),
    )
    targeted = [
        t
        for t in TIPS
        if (t.get("purposes") or t.get("categories"))
        and fits(t)
        and t["kind"] != "season"
    ]
    howto = [t for t in TIPS if t["kind"] == "howto" and fits(t)]
    law = [t for t in TIPS if t["kind"] == "law" and not t.get("categories")]
    mixed = [
        x for i, h in enumerate(howto) for x in ([h, law[i]] if i < len(law) else [h])
    ]
    out, seen = [], set()
    for t in [*season, *targeted, *mixed]:
        if t["id"] not in seen:
            seen.add(t["id"])
            out.append(_public(t))
    return out[:limit]


def _public(t: dict) -> dict:
    return {
        "id": t["id"],
        "kind": t["kind"],
        "title": t["title"],
        "body": t.get("body"),
        "action": t.get("action"),
        "source": t.get("source"),
        "checked_at": CHECKED if t["kind"] in ("platform", "law") else None,
    }
