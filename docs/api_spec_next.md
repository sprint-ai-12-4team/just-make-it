# API 추가 명세 (서비스 → 서빙)

상태: **초안 (PM·서비스)**. 서빙 리뷰 후 확정되면 `api_spec.md`에 합칩니다.
공통 규칙(Base URL, `X-Client-Id`, 오류 형식)은 [`api_spec.md` 1장](api_spec.md#1-공통-규칙)과 같습니다.

## 한눈에 보기

| # | 엔드포인트 | 하는 일 | 서비스(DB) | 서빙(라우트) |
|---|---|---|---|---|
| 1 | `POST /events` | 다운로드·링크 복사·다시 만들기 등 사용 기록 | `db.add_event` ✅ | 라우트 연결 |
| 2 | `POST /generations/{id}/image` | 브라우저에서 고친 그림(배경 지우기·글자)을 서버에 저장 → 공유 링크에도 반영 | `db.replace_image` ✅ | 라우트 연결 |
| 3 | `GET /generations/{id}/family` | 같은 원본에서 다시 만든 결과 목록 | `db.family` ✅ | 라우트 연결 |
| 4 | `/generate`의 `keep_product` | 상품 사진 그대로, 배경 장면만 AI로 (10-30 추가) | 프론트 합성 ✅ | 장면 프롬프트·`product_url` (모델·서빙) |

- ✅ = 서비스 쪽 함수와 테스트 준비 완료. 서빙은 **라우트에서 함수만 부르면** 됩니다 (모델·GPU 호출 없음).
- 1~3은 일일 생성 한도에 세지 않습니다.
- 프론트는 1~3이 아직 없어도(`404`) 지금처럼 동작합니다. 기록은 버리고, 저장은 안내만 띄우고, 목록은 브라우저 기록으로 대신합니다.

---

## 1. `POST /events` — 사용 기록

채택률(발표 지표)과 다음 학습용 선호 데이터를 쌓습니다. 실패해도 화면에는 영향 없음.

**요청** JSON

| 필드 | 타입 | 필수 | 설명 |
|---|---|:-:|---|
| `generation_id` | string | ✅ | 결과 `id` |
| `type` | string | ✅ | 아래 표 |
| `detail` | object | | 추가 정보 (자유 형식, 4KB 이하) |

| `type` | 언제 | `detail` 예 |
|---|---|---|
| `download` | "내 기기에 저장" | `{"edited": true}` (직접 고친 그림이면) |
| `copy_link` | "링크 복사" | |
| `remake` | "다시 만들기" | `{"adjustments": ["더 밝게"]}` |
| `edit_text` | 글자 직접 고치기 시작 | |
| `cutout` | 배경 지우고 색 채우기 완료 | |
| `pick_copy` | 추천 문구 중 하나를 고름 | `{"index": 1, "copy": "…"}` |

```json
{"generation_id": "6f1c2b0e-...", "type": "download", "detail": {"edited": false}}
```

**응답** `204` (본문 없음)

- 모르는 `type`·없는 `generation_id` → `400`
- `download`·`copy_link`이면 `generations.downloaded_at`(첫 시각)도 함께 채웁니다.

## 2. `POST /generations/{id}/image` — 고친 그림 저장

지금은 배경 지우기·글자 직접 고치기 결과가 **그 브라우저에만** 있어서, 링크를 받은 사람은 서버가 처음 만든 그림을 봅니다. 고친 그림을 올려 링크에도 반영합니다.

**요청** `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:-:|---|
| `image` | file | ✅ | 글자까지 얹은 최종 그림. PNG, 10MB 이하 |
| `background` | file | | 글자 없는 그림 (배경을 지웠을 때). 보내면 `background_url`도 바뀌어, 이후 `POST /generations/{id}/text`가 지운 배경 위에 글자를 얹음 |
| `message` | string | | 그림에 얹은 문구. 보내면 응답 `message`가 바뀌어 다시 고치기·다시 만들기가 이어 씀 |

**응답** `200` — `GET /generations/{id}`와 같은 형식. `image_url`이 **새 주소** (`/text`와 같은 방식, 캐시 회피). `edited: true` (이 필드는 `GET /generations/{id}`에도 추가, 기본 `false`).

- 크기는 원래 결과와 같아야 함 (`width`×`height`). 다르면 `400`
- 없는 `id` `404`, `processing`·`error`인 결과 `409`, 10MB 초과 `413`, PNG가 아니면 `415`
- ponytail: 지금은 아무나 링크만 알면 덮어쓸 수 있음 (`/text`와 같음). 로그인(S3) 때 `client_id` 확인 추가

## 3. `GET /generations/{id}/family` — 같은 원본에서 만든 결과

`parent_id`를 거슬러 맨 처음 결과를 찾고, 그 아래 모든 결과를 돌려줍니다 (만든 순서).

**응답** `200`

```json
{
  "items": [
    {"id": "a1...", "parent_id": null, "image_url": "https://.../a1.png", "created_at": "2026-10-26T09:30:00.000Z"},
    {"id": "b2...", "parent_id": "a1...", "image_url": "https://.../b2.png", "created_at": "2026-10-26T09:31:10.000Z"}
  ]
}
```

- 성공한 결과만, 최대 50개. 상세페이지 섹션은 제외
- 없는 `id` `404`. 혼자인 결과도 `items`에 자기 1개가 옴

---

## 4. `keep_product` — 내 상품 사진 그대로, 배경만 AI로 (S1)

AI가 상품을 다시 그리면 모양·로고가 바뀌어 못 쓰는 경우가 많습니다. 상품은 **사용자 사진의 픽셀 그대로** 두고, 서버는 **상품 없는 장면**만 그립니다. 합치기(상품 놓기·그림자·글자)는 프론트가 하고 `POST /generations/{id}/image`로 저장합니다.

```
프론트: 사진 → 배경 지우기(투명 PNG) ─┐
                                       ├─ POST /generate (keep_product=true, reference_image=투명 PNG)
서버:   상품 없는 장면 1장 생성 ───────┘     → background_url(장면) + product_url(받은 투명 PNG)
프론트: 장면 + 상품(가운데 아래) + 그림자 + 글자 → POST /generations/{id}/image (image, background, message)
```

**요청** — `/generate`·`POST /generations`에 필드 1개 추가

| 필드 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `keep_product` | bool | `false` | `true`면 `reference_image`(배경이 투명한 PNG·WEBP) 필수. 없으면 `400` |

**서버(모델·서빙)가 할 일**
- 프롬프트: 상품 없이 장면만, **가운데 아래(가로 60%·세로 55%)를 비운 구도**, 글자 없음. 참고 사진은 klein에 넣지 않음 (넣으면 상품을 다시 그림) → VRAM 추가 없음, 1장 그대로
- 참고 사진은 지금처럼 저장 (`reference_image_path`). `parent_id`로 다시 만들면 같은 상품을 다시 씀
- 글자: `text_layout.position`은 `top` 고정 (상품이 아래에 오므로)
- 응답·조회에 `product_url` 추가 (`keep_product`가 아니면 `null`)

**응답** — 지금 형식 + `product_url`

```json
{"id": "…", "image_url": "…/id.png", "background_url": "…/id-bg.png", "product_url": "…/id-product.png", "text_layout": {"position": "top", "font": "jua", "size_scale": 1.0}, "edited": false}
```

- 프론트는 `product_url`이 있고 `edited`가 `false`면 바로 합쳐서 저장합니다. 이후 글자 고치기·배경 지우기는 합친 그림(`background_url`)에서 이어집니다.
- 서버가 아직 `keep_product`를 모르면 필드를 무시하고 보통 결과를 줍니다 (`product_url` 없음) → 프론트는 보통 결과로 보여 줌.
- 일일 한도·비용은 보통 생성 1장과 같음.

---

## 나중에 (모델·서빙 준비 후 따로 정함)

| 항목 | 필요한 것 | 로드맵 |
|---|---|---|
| 가게 키트 (가게명·대표색·로고) | 로그인 필요 → 보류 | S3 |

- 단일 이미지 요청은 **1장만** 만듭니다 (`count` 같은 여러 장 생성 없음). 여러 장은 GPU를 그만큼 더 쓰므로 상세페이지(섹션 5장)에만 씁니다. 더 보고 싶으면 사용자가 "한 번 더 만들기"로 1장씩 만들고, 같은 원본 목록(3장)에서 비교합니다.
