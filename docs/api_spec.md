# API 스펙 — just-make-it

> 상태: **초안 (PM)**. 팀 리뷰 후 확정. 변경은 PR로 제안해 주세요.
> 기준 코드: `frontend/lib/api.ts`, `core/pipeline.py`, `core/copywriter.py`, `core/prompt_builder.py`

---

## 1. 공통 규칙

| 항목 | 규칙 |
|------|------|
| Base URL | 로컬 `http://localhost:8000` / 프론트는 `NEXT_PUBLIC_API_URL` 사용 |
| 형식 | JSON (`application/json`). 참고 이미지가 있을 때만 `multipart/form-data` |
| 필드 이름 | `snake_case` |
| 사용자 구분 | 헤더 `X-Client-Id: <uuid>` — 브라우저가 처음 접속할 때 만들어 `localStorage`에 저장. 로그인 없음 (MVP) |
| 에러 | FastAPI 기본 형식 `{"detail": "사용자에게 보여줄 한글 메시지"}` |
| 생성 경로 | 로컬 GPU / OpenAI 중 어디서 만들었는지는 `source`로만 알려줌. **화면에는 노출하지 않음** |
| 모델 이름 | `image_model`·`text_model` 값은 화면에 노출하지 않음. 프론트는 "빠르게 / 더 정교하게" 같은 이름으로만 보여줌 |
| 동기 / 비동기 | 단일 이미지는 **동기**(`POST /generate`)와 **비동기**(`POST /generations`, `202` → `GET /generations/{id}` 폴링) 둘 다 됨 (V3, 10-28). 상세페이지(`/detail-pages`)는 **비동기** |

---

## 2. 엔드포인트 요약

| 메서드 | 경로 | 용도 | 화면 |
|--------|------|------|------|
| `GET` | `/health` | 서버 상태 확인 (docker healthcheck) | — |
| `POST` | `/copies` | 홍보 문구 3개 추천 | ② 기본 정보 입력 |
| `POST` | `/generate` | 광고 이미지 생성 (다시 만들기·수정 포함), 동기 | ④ 생성 요청 |
| `POST` | `/generations` | 광고 이미지 생성, **비동기** (문구 먼저, 그림 나중) — V3 | ④ 생성 요청 |
| `GET` | `/generations/{id}` | 생성 결과 다시 조회 (비동기 생성 폴링 포함) | ⑤ 결과 확인 |
| `GET` | `/generations/{id}/family` | 같은 원본에서 다시 만든 결과 목록 — S2 | ⑤ 나란히 보기·되돌리기 |
| `POST` | `/generations/{id}/text` | 글자(문구·위치·글꼴·크기)만 바꿔 다시 얹기 | ⑤ 결과 확인 |
| `POST` | `/generations/{id}/image` | 브라우저에서 고친 그림(배경 지우기·글자)을 서버에 저장 — S7 | ⑤ 결과 확인 |
| `POST` | `/events` | 다운로드·링크 복사·다시 만들기 등 사용 기록 — S4 | ⑤ 결과 확인 |
| `GET` | `/stats` | 채택률 지표 (생성 · 다운로드 · 직접 고침 · 다시 만들기) — S4 | — (운영·발표) |
| `POST` | `/detail-pages` | 상세페이지 생성 시작 (비동기) | ④ 생성 요청 (커머스) |
| `GET` | `/detail-pages/{id}` | 상세페이지 진행 상황·결과 조회 (폴링) | ④ 대기 → ⑤ 결과 확인 |
| `POST` | `/detail-pages/{id}/sections/{index}` | 섹션 1개만 다시 생성 | ⑤ 결과 확인 |

---

## 3. 엔드포인트 상세

### `GET /health`

```json
200 {"status": "ok"}
```

### `POST /copies` — 홍보 문구 추천

**요청**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `product_name` | string | ✅ | 가게·상품 이름 |
| `message` | string | ✅ | 핵심 메시지 (예: `주말 20% 할인`) |
| `style` | string | | 분위기 칩 값 ([5. 공통 값](#5-공통-값)) |
| `text_model` | string | | `gemma-4-12b-it`(기본) · `openai-gpt-5.6-luna` |

```json
{"product_name": "동네꽃집", "message": "주말 20% 할인", "style": "밝고 경쾌한"}
```

**응답** `200`

```json
{"copies": ["이번 주말엔 꽃 한 다발 20% 할인", "주말, 꽃으로 20% 더 행복하게", "꽃 고르는 주말, 20% 할인"]}
```

- 최대 3개. 모델 출력에 따라 더 적을 수 있음.
- 할인율·가격·날짜는 입력값을 그대로 유지함.

### `POST /generate` — 광고 이미지 생성

**요청**

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|:----:|--------|------|
| `purpose` | string | ✅ | | 광고 목적 |
| `product_name` | string | ✅ | | 가게·상품 이름 |
| `message` | string | ✅ | | 이미지에 넣을 문구 (`/copies` 결과를 써도 됨) |
| `style` | string | | `null` | 분위기 칩 값 |
| `adjustments` | string[] | | `[]` | "조금 수정하기" 칩 값 |
| `parent_id` | string | | `null` | 다시 만들기·수정할 때 원본 결과의 `id` |
| `image_model` | string | | `flux2-klein-4b` | `flux2-klein-4b` · `openai-image-2.5-flare`. 로컬이 바쁘면 서버가 OpenAI로 넘길 수 있음 (`source`로 기록) |
| `reference_image` | file | | | 상품 사진. **multipart일 때만**. PNG·JPG·WEBP, 10MB 이하 |

- **다시 만들기**: 같은 입력 + `parent_id`
- **조금 수정하기**: 같은 입력 + `parent_id` + `adjustments`
- multipart에서 `adjustments`는 같은 이름으로 여러 번 보냄 (`adjustments=더 밝게&adjustments=배경 단순하게`)

```json
{
  "purpose": "instagram",
  "product_name": "소금빵",
  "message": "신메뉴 출시",
  "style": "따뜻한",
  "adjustments": [],
  "parent_id": null
}
```

**응답** `200`

```json
{
  "id": "6f1c2b0e-8a7d-4c1e-9b2f-3d5e7a9c1b20",
  "status": "success",
  "image_url": "https://.../6f1c2b0e-....png",
  "background_url": "https://.../6f1c2b0e-...-bg.png",
  "message": "신메뉴 출시",
  "text_layout": {"position": "top", "font": "yeonsung", "size_scale": 1.0},
  "source": "openai",
  "width": 1024,
  "height": 1024
}
```

| 필드 | 설명 |
|------|------|
| `id` | 결과 ID (uuid). 다시 만들기의 `parent_id`, 결과 조회에 사용 |
| `image_url` | **글자를 얹은 최종 이미지**. 화면 표시·다운로드·링크 복사에 그대로 사용 |
| `background_url` | 글자 없는 원본 이미지. 글자 고치기는 서버가 이 이미지에 다시 얹음 |
| `message` | 실제로 얹은 문구. `텍스트 짧게`를 고르면 줄어든 문구가 옴 |
| `text_layout` | 실제로 얹은 글자 위치·글꼴·크기 ([5. 공통 값](#text_layout--글자-위치글꼴크기)). 결과 화면의 "글자 고치기" 초기값 |
| `source` | `local` (GPU) 또는 `openai`. 통계용, 화면 노출 금지 |

> `/generate`는 **동기 응답**입니다 (보통 10~30초). 기다리는 동안 문구·진행 상황을 보여주려면 같은 본문으로 [`POST /generations`](#post-generations--광고-이미지-생성-비동기-v3)를 씁니다.
> 30초를 넘는 작업(상세페이지)은 [`POST /detail-pages`](#post-detail-pages--상세페이지-생성-시작)의 비동기 방식을 씁니다.

### `POST /generations` — 광고 이미지 생성 (비동기, V3)

`/generate`와 **요청 본문·검사·라우팅이 같고**, 기다리지 않고 바로 `202`를 돌려줍니다. 프론트는 문구를 먼저 보여주고 `GET /generations/{id}`를 **2초마다** 조회합니다 (`status`가 `processing`이 아니면 멈춤).

**응답** `202`

```json
{"id": "6f1c2b0e-...", "status": "processing", "message": "신메뉴 출시", "width": 1024, "height": 1024, "estimated_seconds": 24.0}
```

| 필드 | 설명 |
|------|------|
| `message` | 입력한 문구. 이미지보다 먼저 화면에 보여줄 수 있음 (`텍스트 짧게`면 완료 후 조회 응답의 `message`로 바뀔 수 있음) |
| `width`, `height` | 결과 이미지 크기. 자리(비율)를 미리 잡아둘 때 사용 |
| `estimated_seconds` | 끝날 때까지 남은 예상 시간(초). 대략적인 값 |

- 에러는 `/generate`와 같음 (`400`·`413`·`415`·`422`·`429`, 대기열이 가득 차면 `503`). 생성 자체의 실패는 조회 응답의 `status: "error"`로 알 수 있음
- 동기 `/generate`와 달리 응답을 기다리다 작업을 취소하지 않음 → 화면을 닫았다 와도 같은 `id`로 결과를 볼 수 있음

### `GET /generations/{id}` — 결과 조회

결과 화면 새로고침, 링크 공유 시 사용.

**응답** `200` — `/generate` 응답과 같은 형식 + 입력값

```json
{
  "id": "6f1c2b0e-...",
  "status": "success",
  "image_url": "https://.../6f1c2b0e-....png",
  "background_url": "https://.../6f1c2b0e-...-bg.png",
  "message": "신메뉴 출시",
  "text_layout": {"position": "top", "font": "yeonsung", "size_scale": 1.0},
  "source": "openai",
  "width": 1024,
  "height": 1024,
  "parent_id": null,
  "created_at": "2026-10-20T09:30:00.000Z",
  "input": {"purpose": "instagram", "product_name": "소금빵", "message": "신메뉴 출시", "style": "따뜻한", "adjustments": []}
}
```

- `status`: `success` | `processing` | `error`
- 없는 `id`면 `404`
- 글자를 고쳤으면 고친 뒤의 `image_url`·`message`·`text_layout`이 옴 (링크 공유도 최신 상태)
- `processing`이면 `progress`가 함께 옴 (V3). 그 밖에는 `null`

  ```json
  "progress": {"stage": "queued", "jobs_ahead": 2, "estimated_seconds": 60.0}
  ```

  | 필드 | 값 |
  |------|----|
  | `stage` | `queued` (차례 기다리는 중) · `running` (만드는 중) |
  | `jobs_ahead` | 먼저 처리될 작업 수. 화면 예: "앞에 2건 기다리는 중" |
  | `estimated_seconds` | 남은 예상 시간(초). 화면 예: "약 1분" |

  서버를 다시 켜기 전에 접수한 작업처럼 진행 상황을 모르면 `null`

### `GET /generations/{id}/family` — 같은 원본에서 만든 결과 (S2)

결과 화면 "나란히 보기 · 되돌리기". `parent_id`를 거슬러 맨 처음 결과를 찾고, 그 아래 모든 결과를 돌려줍니다 (만든 순서). 프론트 `lib/family.ts`(브라우저 기록)를 대체하면 다른 기기·공유 링크에서도 같은 목록이 보입니다.

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
- 없는 `id`(상세페이지 섹션 `id` 포함) `404`. 혼자인 결과도 `items`에 자기 1개가 옴

### `POST /generations/{id}/text` — 글자만 다시 얹기

결과 화면 "글자 고치기". **이미지는 다시 만들지 않고** 서버가 `background_url` 이미지에 글자만 다시 얹습니다 (GPU·OpenAI 호출 없음, 1초 이내). 일일 생성 한도에 세지 않음.

**요청** — JSON. 바꿀 필드만 보내면 나머지는 지금 값 유지

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | 얹을 문구. 빈 문자열이면 `400` |
| `position` | string | `top` · `middle` · `bottom` |
| `font` | string | `jua` · `yeonsung` · `batang` · `dodum` · `blackhan` |
| `size_scale` | number | 글자 크기 배율 `0.6` ~ `1.6` |

```json
{"message": "이번 주말만 20% 할인", "position": "bottom", "font": "blackhan"}
```

**응답** `200` — `GET /generations/{id}`와 같은 형식. `image_url`이 **새 주소**로 바뀜 (브라우저 캐시 회피)

- 없는 `id`면 `404`, 아직 `processing`이거나 `error`인 결과면 `409`
- 분위기(`style`)별 색·테두리·장식은 그대로 두고 글꼴만 바꿈
- 문구에 글꼴에 없는 글자가 있으면 서버가 `dodum`으로 대신 씀 → 응답 `text_layout.font`가 실제 값

### `POST /generations/{id}/image` — 고친 그림 저장 (S7)

배경 지우기·글자 직접 고치기 결과는 그 브라우저에만 있어서, 링크를 받은 사람은 서버가 처음 만든 그림을 봅니다. 고친 그림을 올려 링크에도 반영합니다. 이미지는 다시 만들지 않고 일일 생성 한도에 세지 않음.

**요청** `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `image` | file | ✅ | 글자까지 얹은 최종 그림. PNG, 10MB 이하 |
| `background` | file | | 글자 없는 그림 (배경을 지웠을 때). 보내면 `background_url`도 바뀌어, 이후 `POST /generations/{id}/text`가 지운 배경 위에 글자를 얹음 |
| `message` | string | | 그림에 얹은 문구. 보내면 응답 `message`가 바뀌어 다시 고치기·다시 만들기가 이어 씀 |

**응답** `200` — `GET /generations/{id}`와 같은 형식. `image_url`이 **새 주소** (`/text`와 같은 방식, 캐시 회피). `edited: true` (`GET /generations/{id}`에도 있음, 기본 `false`)

- 크기는 원래 결과와 같아야 함 (`width`×`height`, `image`·`background` 모두). 다르면 `400`
- 없는 `id` `404`, `processing`·`error`인 결과 `409`, 10MB 초과 `413`, PNG가 아니면 `415`, `image`가 없으면 `422`
- `text_layout`은 그대로 둠 (서버 글자 고치기의 처음 값)
- ponytail: 지금은 아무나 링크만 알면 덮어쓸 수 있음 (`/text`와 같음). 로그인(S3) 때 `client_id` 확인 추가

### `POST /events` — 사용 기록 (S4)

채택률(발표 지표)과 다음 학습용 선호 데이터를 쌓습니다. 실패해도 화면에는 영향 없음 (프론트는 실패를 무시).

**요청** JSON

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `generation_id` | string | ✅ | 결과 `id` |
| `type` | string | ✅ | 아래 표 |
| `detail` | object | | 추가 정보 (자유 형식, 4KB 이하) |

| `type` | 언제 | `detail` 예 |
|--------|------|-------------|
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

- 모르는 `type`, 없는 `generation_id`, `detail`이 객체가 아니거나 4KB 초과 → `400`
- 누를 때마다 1건씩 쌓임. 사용자는 `X-Client-Id`로 남김
- `download`·`copy_link`이면 `generations.downloaded_at`(첫 시각)도 함께 채움
- 일일 생성 한도에 세지 않음

### `GET /stats` — 채택률 지표 (S4, 서빙 추가)

발표·운영용 집계. 단일 이미지 결과만 (상세페이지 섹션 제외).

| 쿼리 | 기본값 | 설명 |
|------|--------|------|
| `days` | `7` | 최근 며칠(한국 날짜, 오늘 포함). 1~90 |

**응답** `200`

```json
{
  "days": [{"date": "2026-10-28", "generated": 40, "downloaded": 22, "edited": 12, "remade": 15, "download_rate": 0.55, "edit_rate": 0.3, "remake_rate": 0.375}],
  "total": {"date": "total", "generated": 40, "downloaded": 22, "edited": 12, "remade": 15, "download_rate": 0.55, "edit_rate": 0.3, "remake_rate": 0.375}
}
```

| 필드 | 뜻 |
|------|----|
| `generated` | 성공한 결과 수 |
| `downloaded` | 그중 다운로드 또는 링크 복사된 결과 수 |
| `edited` | 그중 글자 직접 고치기·배경 지우기(`edit_text`·`cutout`)를 했거나 고친 그림을 저장한 결과 수 |
| `remade` | 그중 다시 만들기·조금 수정하기의 원본이 된 결과 수 (`parent_id` 기준) |
| `*_rate` | `generated` 대비 비율 |

### `POST /detail-pages` — 상세페이지 생성 시작

커머스 상세페이지용. 섹션 5개(대표 · 특징 ×3 · 마무리)의 문구와 이미지를 만듭니다. 30초 이상 걸리므로 **바로 `202`를 돌려주고**, 결과는 `GET /detail-pages/{id}`로 받습니다.

**요청** — JSON, 참고 사진이 있으면 multipart

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `product_name` | string | ✅ | 상품 이름 |
| `message` | string | ✅ | 핵심 메시지 |
| `features` | string[] | | 상품 특징 (최대 3개). 비우면 텍스트 모델이 만듦 |
| `style` | string | | 분위기 칩 값 |
| `image_model` | string | | `/generate`와 같음. 섹션 재생성도 이 값을 그대로 씀 |
| `reference_image` | file | | 상품 사진 (multipart만). 조건은 `/generate`와 같음 |

```json
{"product_name": "수제 딸기잼", "message": "국산 딸기 100% 신상품", "features": ["무첨가", "소량 생산", "선물 포장"], "style": "따뜻한"}
```

**응답** `202`

```json
{"id": "a3d9...", "status": "processing"}
```

- 한 사용자(`X-Client-Id`)당 **진행 중인 상세페이지는 1개**. 이미 진행 중이면 `409`.

### `GET /detail-pages/{id}` — 진행 상황·결과 조회

프론트는 **2초마다** 호출하고, `status`가 `processing`이 아니면 멈춥니다. 섹션이 끝나는 대로 화면을 채웁니다.

**응답** `200`

```json
{
  "id": "a3d9...",
  "status": "processing",
  "progress": {"done": 2, "total": 5},
  "sections": [
    {"index": 0, "role": "hero",    "status": "success",    "title": "국산 딸기 100%, 그대로 담았어요", "body": "설탕 말고 딸기 맛만 남겼습니다.", "image_url": "https://.../a3d9-0.png", "source": "local"},
    {"index": 1, "role": "feature", "status": "success",    "title": "무첨가", "body": "보존료·색소 없이 만들어요.", "image_url": "https://.../a3d9-1.png", "source": "local"},
    {"index": 2, "role": "feature", "status": "processing", "title": "소량 생산", "body": "매일 필요한 만큼만 끓여요.", "image_url": null, "source": null},
    {"index": 3, "role": "feature", "status": "pending",    "title": null, "body": null, "image_url": null, "source": null},
    {"index": 4, "role": "closing", "status": "pending",    "title": null, "body": null, "image_url": null, "source": null}
  ],
  "created_at": "2026-10-20T09:30:00.000Z"
}
```

| 필드 | 값 |
|------|----|
| 페이지 `status` | `processing` (진행 중) · `success` (모든 섹션 끝남. 일부 섹션이 `error`일 수 있음) · `error` (문구 생성 실패 등 전체 실패) |
| 섹션 `status` | `pending` (문구 대기) → `processing` (문구 완료, 이미지 생성 중) → `success` · `error` |
| 섹션 `role` | `hero` · `feature` · `closing` |
| `title`, `body` | 프론트가 이미지 위에 얹을 문구 |

- 2분이 지나도 `processing`이면 프론트는 "조금 더 걸리고 있어요" 안내 + 새로고침 버튼을 보여줌.
- 없는 `id`면 `404`.

### `POST /detail-pages/{id}/sections/{index}` — 섹션 다시 생성

실패한 섹션을 재시도하거나 마음에 안 드는 섹션만 다시 만듭니다. **문구는 그대로 두고 이미지만** 다시 생성합니다.

**요청**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `adjustments` | string[] | | "조금 수정하기" 칩 값 |

**응답** `202` — 해당 섹션의 `status`가 `processing`으로 바뀜. 결과는 `GET /detail-pages/{id}`로 확인.

- 페이지가 아직 `processing`이면 `409`.

---

## 4. 에러

| 코드 | 언제 | `detail` 예시 |
|------|------|---------------|
| `400` | 필수값이 비어 있음 | `상품 이름과 핵심 메시지는 꼭 입력해야 합니다.` |
| `404` | 없는 결과 ID | `결과를 찾을 수 없어요.` |
| `409` | 상세페이지가 이미 진행 중 / 아직 안 끝난 결과의 글자 고치기 | `만들고 있는 상세페이지가 있어요. 끝나면 다시 시도해 주세요.` |
| `413` | 참고 사진이 10MB 초과 | `사진은 10MB 이하로 올려 주세요.` |
| `415` | PNG·JPG·WEBP가 아닌 사진 | `참고 사진은 PNG, JPG, WEBP 파일만 사용할 수 있습니다.` |
| `422` | 타입·허용값 오류 (FastAPI 자동) | — |
| `429` | 일일 생성 한도 초과 (한도 미정) | `오늘 만들 수 있는 횟수를 다 썼어요.` |
| `503` | 로컬·OpenAI 모두 실패 | `잠시 후 다시 시도해 주세요.` |

- 프론트는 `503`이면 재시도 버튼을 보여줌.
- 내부 예외 메시지(API 키, 스택 등)는 `detail`에 넣지 않음.

---

## 5. 공통 값

### `purpose` — 광고 목적

| 값 | 화면 이름 | 크기 (가로×세로) |
|----|-----------|------------------|
| `instagram` | 인스타그램 | 1024×1024 |
| `commerce` | 스마트스토어 · 쿠팡 | 1024×1024 |
| `youtube` | 유튜브 썸네일 | 1536×864 |
| `kakao` | 카카오톡 · 문자 | 1024×1536 |
| `free` | 자유롭게 만들기 | 1024×1024 |

### 글자 처리 — 서버가 얹고, 사용자가 고침 (2026-10-22 결정, 10-20 결정 대체)

- **이미지 모델은 글자 없는 이미지만 만듦** ("no text, no letters"). 문구는 서버(core `text_overlay.py`, PIL)가 분위기별 디자인으로 얹음
- 응답에 최종 이미지(`image_url`) + 글자 없는 원본(`background_url`) + 문구(`message`) + 위치·글꼴·크기(`text_layout`)를 모두 줌
- 결과 화면은 기본으로 `image_url`을 그대로 씀. 사용자가 **"글자 직접 고치기"**를 누르면 프론트가 `background_url` 위에 `<canvas>`로 문구를 얹고 끌어서 옮김 (스타일 10종 `frontend/lib/textStyles.ts`, 1~5번은 core `DESIGNS`와 같은 계열, 글꼴은 `frontend/public/fonts`) — 10-22 PM 결정
- 직접 고친 결과는 `POST /generations/{id}/image`로 서버에 저장하면 링크 공유에도 반영됨 (S7, 10-26). `POST /generations/{id}/text`는 서버 재렌더용으로 유지, 프론트는 현재 안 씀
- 이유: 글자 디자인(테두리·그림자·장식·기울기)을 서버 한 곳에서만 그림 → 미리보기 = 다운로드 = 공유 이미지. 프론트 canvas와 결과가 어긋나지 않음
- `generation_mode`는 계속 **삭제** 상태 (항상 글자를 얹음). `글자 더 크게` 칩은 `size_scale: 1.25`로 대체
- 상세페이지 섹션은 아직 프론트 canvas로 얹음 (단일 이미지 먼저 적용)

### `text_layout` — 글자 위치·글꼴·크기

| 필드 | 값 | 화면 이름 |
|------|----|-----------|
| `position` | `top` · `middle` · `bottom` | 위 · 가운데 · 아래. 처음엔 서버가 물체가 적은 쪽(`top`/`bottom`)을 고름 |
| `font` | `jua` · `yeonsung` · `batang` · `dodum` · `blackhan` | 주아 · 연성 · 고운바탕 · 고운돋움 · 검은고딕. 처음엔 분위기(`style`)의 글꼴 |
| `size_scale` | `0.6` ~ `1.6` (기본 `1.0`) | 글자 크기. 화면에선 "글자 더 크게" = `1.25` |

### `style` — 분위기 칩

`밝고 경쾌한` · `고급스러운` · `따뜻한` · `심플한` · `강렬한`
목록에 없는 값도 받음 (그대로 프롬프트에 사용).

### `adjustments` — 조금 수정하기 칩

| 값 | 비고 |
|----|------|
| `텍스트 짧게` | 문구를 줄여 얹고 응답 `message`로 전달 (이미지는 새로 생성) |
| `더 밝게` | |
| `배경 단순하게` | |

---

## 6. 미결 사항

- [ ] 상세페이지 섹션 수(5)·섹션 이미지 크기 확정 — PM·모델
- [ ] 상세페이지 작업 실행 방식 (FastAPI `BackgroundTasks` vs 별도 대기열), 서버 재시작 시 진행 중이던 작업 처리 — 서빙
- [x] 상세페이지 저장 구조 → `detail_pages` 테이블 + 섹션 이미지는 `generations` 행 (`detail_page_id`, `section_index`). `docs/schema.sql` 참고 (코드가 읽는 위치는 `service/schema.sql`로 이동 예정)
- [x] 모델 선택 → `image_model`(`/generate`·`/detail-pages`), `text_model`(`/copies`). 프론트는 고정 목록 사용, `GET /models`는 상주 모델이 바뀔 때 추가 — 서빙
- [x] 저장소 → **VM 로컬 디스크** (DB: SQLite, 이미지: `$DATA_DIR/images`, `/images/{id}.png`로 제공, 만료 없음). 코드 `service/db.py`, `service/storage.py`
- [ ] 일일 생성 한도 값, 비로그인 허용 여부 — PM
- [ ] 참고 사진 최대 크기 10MB 확정 — 서빙·모델
- [ ] 프리미엄(OpenAI 강제) 요청 필드 필요 여부 — PM·서비스
- [ ] 글자 자유 위치(드래그) — 지금은 위·가운데·아래 3곳. 필요하면 `text_layout`에 `x`·`y`(0~1 비율) 추가 — PM·모델
- [x] 다시 만들기 때 원본 참고 사진: 조회 응답에 사진이 없어 프론트가 다시 못 보냄 → 서버가 `parent_id`의 참고 사진을 재사용 — 서빙
- [x] 사용 기록·고친 그림 저장·같은 원본 목록 → PM·서비스 추가 명세(api_spec_next, 10-28) 그대로 반영. 서비스 함수 `db.add_event`·`db.replace_image`·`db.family` + 서빙 라우트
- [ ] 같은 원본 목록(`/family`)은 결과 `id`만 알면 누구나 볼 수 있음 (공유 링크를 받은 사람도 이전 시안을 봄). 로그인(S3) 때 `client_id`로 제한 — PM
- [ ] `/stats`는 인증 없이 열려 있음 (합계 숫자만 나옴). 외부에 숨기려면 관리자 키 추가 — PM·서빙
- [ ] 프론트 전환: 비동기 생성(`POST /generations` + 폴링, 선택), 나란히 보기(`/family`), 사용 기록(`/events`), 고친 그림 저장(`/image`) 호출 — 서비스
- [ ] 내 사진 그대로 배경만 바꾸기: `/generate`에 `keep_product: bool` (S1·M5) — 모델·서빙 준비 후
- [x] 단일 이미지는 요청당 1장 (여러 장 후보 생성 없음, V4 보류). 비교는 "한 번 더 만들기" + 같은 원본 목록으로 — PM 10-28
