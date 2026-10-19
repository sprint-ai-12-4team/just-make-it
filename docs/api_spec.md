# API 명세 (초안)

> 작성: 서빙(장한빈) · 상태: **초안 — 프론트·서비스 개발·PM 리뷰 필요**
> 구현: `src/just_make_it/serving/` · 서버 실행 후 `/docs`(Swagger)에서도 확인 가능

## 공통

- Base URL: 개발 `http://localhost:8000`
- 인증: 없음 (MVP)
- 에러 응답: `{"detail": "유저에게 보여줄 한국어 메시지"}`

| 코드 | 의미 |
| --- | --- |
| 200 | 성공 (생성 완료) |
| 202 | 접수됨, 아직 생성 중 → `GET /jobs/{job_id}`로 조회 |
| 404 | 작업 없음 (완료 후 1시간 지나면 만료) |
| 422 | 입력 오류 |
| 429 | 하루 생성 한도 도달 |
| 502 | 생성 실패 |
| 503 | 대기열 가득 참 |

---

## POST /generate

광고 이미지 생성을 요청한다. 서버 안에서 core의 `generate_ad_image()`를 호출한다.
`wait`초 안에 끝나면 결과를, 아니면 `job_id`를 반환한다.

### Query

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `wait` | number | 60 | 결과를 기다려 줄 최대 시간(초). `0`이면 바로 `job_id` 반환 |

### Body

`application/json`, 또는 참고 사진이 있으면 `multipart/form-data`(같은 필드 + 파일 `reference_image`).

```json
{
  "purpose": "instagram",
  "product_name": "동네빵집",
  "message": "신메뉴 소금빵 출시",
  "style": "따뜻한",
  "generation_mode": "quick",
  "adjustments": ["더 밝게"],
  "premium": false
}
```

| 필드 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `purpose` | ✅ | `instagram` \| `commerce` \| `youtube` \| `kakao` \| `free` | 출력 크기·구도 (core 기준) |
| `product_name` | ✅ | string, 1~50자 | 가게/상품 이름 |
| `message` | ✅ | string, 1~200자 | 핵심 메시지 |
| `style` | | string | 분위기 칩 값 (예: `따뜻한`) |
| `generation_mode` | | `quick` \| `template` \| `canvas` | 기본 `quick`. `quick`만 이미지 안에 문구를 그림 |
| `adjustments` | | string[] | 조금 수정하기 칩. multipart에서는 같은 이름을 여러 번 보내거나 JSON 배열 문자열 |
| `reference_image` | | file, 10MB 이하 | 상품 사진 (서버에서 PNG로 변환) |
| `premium` | | boolean | 고품질 모드. 서버에 프리미엄 모델이 설정돼 있을 때만 적용 |

목적별 크기(core `prompt_builder.py` 기준): instagram·commerce·free 1024×1024, youtube 1536×864, kakao 1024×1536

### 응답 200 — 완료

```json
{
  "status": "success",
  "job_id": "7757112c49704d4e8815c898f9316400",
  "image_url": "http://localhost:8000/results/7757112c49704d4e8815c898f9316400.png",
  "generation_source": "openai",
  "route": "primary",
  "message": "신메뉴 소금빵 출시",
  "model": "gpt-image-2.5-flare"
}
```

| 필드 | 설명 |
| --- | --- |
| `generation_source` | 이미지를 만든 곳: `openai` · `local`(VM 모델) · `mock`(개발용) |
| `route` | 서버가 고른 경로: `primary` · `fallback`(대기·장애 우회) · `premium`(유저 선택) |
| `message` | 이미지에 실제로 쓴 문구. "텍스트 짧게"를 누르면 줄어든 문구 |
| `model` | 실제 사용한 모델 이름 |

> 프론트 결과 화면의 "프리미엄/기본" 표시는 `generation_source`가 아니라 `route === "premium"`으로 판단해야 한다. 지금은 기본 모델도 OpenAI라서 `generation_source`가 항상 `openai`다.

### 응답 202 — 생성 중

```json
{
  "status": "processing",
  "job_id": "53e93ad42ed440fe92331c6dba00d9e9",
  "stage": "queued",
  "queue_position": 1,
  "estimated_wait_seconds": 40.0
}
```

- `stage`: `queued`(대기) · `running`(생성 중)
- `queue_position`: 기본 대기열 순번(1부터). Fallback·프리미엄이거나 생성 중이면 `null`

### 응답 502 — 실패

```json
{ "status": "failed", "job_id": "…", "error": "이미지를 만들지 못했어요. 잠시 후 다시 시도해 주세요." }
```

---

## GET /jobs/{job_id}

작업 상태 조회. 본문은 `/generate`의 success / processing / failed와 같고 HTTP 코드는 항상 200(없으면 404). 권장 폴링 간격 1~2초.

---

## GET /health

```json
{
  "status": "ok",
  "image_backend": "core",
  "primary_model": "core:gpt-image-2.5-flare",
  "primary_ready": true,
  "fallback_model": null,
  "premium_model": null,
  "queue_length": 0,
  "running": 0,
  "estimated_wait_seconds": 20.0,
  "seconds_per_job": 20.0,
  "jobs_today": 12,
  "daily_job_limit": 300,
  "extra_calls_today": 0,
  "extra_daily_limit": 100
}
```

`status: degraded`는 기본 모델이 준비되지 않은 상태다 (API 키 누락, 모델 이름 오류 등). 원인은 서버 로그에 남는다.

---

## GET /results/{job_id}.png

생성 이미지 파일. 서비스 파트의 GCS 업로더가 연결되면 `image_url`이 GCS URL로 바뀐다.

---

## 서버 내부 규칙

| 항목 | 규칙 | 설정 |
| --- | --- | --- |
| 동시 처리 | 기본 모델 작업은 대기열에서 N개씩 처리 | `PRIMARY_CONCURRENCY` (기본 1) |
| 재시도 | 생성 실패 시 같은 모델로 재시도. 입력 오류는 재시도 안 함 | `RETRY_COUNT` (기본 1) |
| Fallback | 예상 대기 > `MAX_WAIT_SECONDS`(30초), 기본 모델 미준비, 재시도 후 실패 | `FALLBACK_IMAGE_MODEL` (비우면 끔) |
| 프리미엄 | 요청의 `premium: true` | `PREMIUM_IMAGE_MODEL` (비우면 기본 모델로 처리) |
| 비용 보호 | 하루 전체 생성 수, Fallback·프리미엄 호출 수 상한 (자정 KST 초기화) | `DAILY_JOB_LIMIT`, `EXTRA_DAILY_LIMIT` |

Fallback·프리미엄 모델 이름은 core `registry.py`의 `IMAGE_MODELS`에 등록된 이름을 쓴다.

---

## 프론트 연동 메모

1. 서버가 기본 60초까지 기다려 주므로 대부분 바로 `success`가 오지만, 대기열이 길면 202 `processing`이 온다. 지금 `create/page.tsx`는 이를 에러로 처리하므로 아래처럼 폴링을 추가한다.

```ts
async function waitForJob(jobId: string): Promise<GenerateSuccessResponse> {
  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    const res = await fetch(`${API_BASE}/jobs/${jobId}`);
    const body = await res.json();
    if (body.status === "success") return body;
    if (body.status === "failed" || !res.ok) throw new Error(body.error ?? body.detail);
    // body.queue_position, body.estimated_wait_seconds로 "앞에 N건 대기 중" 표시 가능
  }
}
```

2. `types.ts`의 성공 응답에 `route`, `message`, `model`을 추가하고, `generation_source`에 `"mock"`을 추가한다.
3. 결과 화면의 수정 칩은 같은 입력에 `adjustments: ["더 밝게"]`를 붙여 `/generate`를 다시 호출하면 된다.
