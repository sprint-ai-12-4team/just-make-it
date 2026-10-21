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
| 동기 / 비동기 | 단일 이미지(`/generate`)는 **동기**. 상세페이지(`/detail-pages`)는 **비동기** (`202` 응답 → 폴링) |

---

## 2. 엔드포인트 요약

| 메서드 | 경로 | 용도 | 화면 |
|--------|------|------|------|
| `GET` | `/health` | 서버 상태 확인 (docker healthcheck) | — |
| `POST` | `/copies` | 홍보 문구 3개 추천 | ② 기본 정보 입력 |
| `POST` | `/generate` | 광고 이미지 생성 (다시 만들기·수정 포함) | ④ 생성 요청 |
| `GET` | `/generations/{id}` | 생성 결과 다시 조회 | ⑤ 결과 확인 |
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
  "message": "신메뉴 출시",
  "source": "openai",
  "width": 1024,
  "height": 1024
}
```

| 필드 | 설명 |
|------|------|
| `id` | 결과 ID (uuid). 다시 만들기의 `parent_id`, 결과 조회에 사용 |
| `image_url` | 이미지 주소. 다운로드·링크 복사에 그대로 사용 |
| `message` | 실제로 쓴 문구. `텍스트 짧게`를 고르면 줄어든 문구가 옴 → 프론트가 이 값을 이미지 위에 얹음 |
| `source` | `local` (GPU) 또는 `openai`. 통계용, 화면 노출 금지 |

> 단일 이미지는 **동기 응답**입니다 (보통 10~30초). 로컬 GPU가 바쁘면 서버가 OpenAI로 바로 넘기므로 폴링하지 않습니다.
> 30초를 넘는 작업(상세페이지)은 [`POST /detail-pages`](#post-detail-pages--상세페이지-생성-시작)의 비동기 방식을 씁니다.

### `GET /generations/{id}` — 결과 조회

결과 화면 새로고침, 링크 공유 시 사용.

**응답** `200` — `/generate` 응답과 같은 형식 + 입력값

```json
{
  "id": "6f1c2b0e-...",
  "status": "success",
  "image_url": "https://.../6f1c2b0e-....png",
  "message": "신메뉴 출시",
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
| `409` | 상세페이지가 이미 진행 중 | `만들고 있는 상세페이지가 있어요. 끝나면 다시 시도해 주세요.` |
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

### 글자 처리 — 이미지 위에 얹기 (2026-10-20 결정)

- **이미지 모델은 글자 없는 이미지만 만듦.** 문구는 프론트가 `<canvas>`로 이미지 위에 얹고, 다운로드도 합친 결과를 저장
- 이유: 로컬 모델은 한글을 못 그림 → 어느 구성안(`pipeline_options.md`)이든 같은 화면으로 동작. 문구 수정은 재생성 없이 즉시
- 그래서 `generation_mode`(quick·template·canvas)는 **삭제**. 글자 위치·크기는 프론트 설정 (서버로 안 보냄)
- 이미지 프롬프트에 "no text, no letters"를 넣어야 함 — 모델
- `image_url`은 프론트가 canvas로 읽으므로 저장소에 **CORS 허용**(`GET`, 프론트 도메인) 필요 — 서비스

### `style` — 분위기 칩

`밝고 경쾌한` · `고급스러운` · `따뜻한` · `심플한` · `강렬한`
목록에 없는 값도 받음 (그대로 프롬프트에 사용).

### `adjustments` — 조금 수정하기 칩

| 값 | 비고 |
|----|------|
| `텍스트 짧게` | 문구를 줄여 응답 `message`로 전달 (이미지는 새로 생성) |
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
- [ ] 다시 만들기 때 원본 참고 사진: 조회 응답에 사진이 없어 프론트가 다시 못 보냄 → 서버가 `parent_id`의 `reference_image_path`를 재사용 — 서빙
