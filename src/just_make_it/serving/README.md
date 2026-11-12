# serving — 모델 서빙

FastAPI로 core의 모델을 API로 열어 주는 층입니다. GPU 한 장으로 여러 사용자를 받으면서 비용이 넘치지 않도록 대기열, 폴백, 제한 시간, 하루 한도를 관리합니다.

API의 요청과 응답 형식은 PM 스펙 [`docs/api_spec.md`](../../../docs/api_spec.md)를 따릅니다.

## 요청 하나가 지나가는 길

1. **router**: 입력 검사, 하루 한도, 비용 상한 확인
2. **작업 큐**: 이미지 생성은 대기열로. 로컬 klein은 한 번에 1건씩 처리
3. **core 호출**: 모델 선택과 로컬 모델 폴백은 core가 담당
4. **기록**: 결과와 비용을 서비스 DB에 남기고 `/stats`로 집계

상담과 문구처럼 텍스트만 쓰는 요청은 대기열을 거치지 않고 바로 텍스트 모델을 부릅니다.

## 엔드포인트

| 묶음 | 엔드포인트 | 하는 일 |
|---|---|---|
| 생성 | `POST /generate` | 동기 생성 (끝날 때까지 기다림) |
| | `POST /generations` | 비동기 생성. 바로 202로 답함 |
| | `GET /generations/{id}` | 진행 단계, 대기 순서, 남은 예상 시간, 결과 |
| 편집 | `POST /generations/{id}/text` | 글자만 다시 얹기 (재생성 없음) |
| | `POST /generations/{id}/restyle` | AI로 꾸미기. flare가 글자만 다시 그림 |
| | `POST /generations/{id}/image` | 편집기에서 고친 이미지 저장 |
| | `GET /generations/{id}/family` | 같은 원본에서 나온 결과 모음 |
| 문구 | `POST /copies` | 광고 문구 3개 추천 |
| | `POST /copies/convert` | 채널별 게시 문구 변환 |
| 상세페이지 | `POST /detail-pages` | 5칸 비동기 생성 |
| | `GET /detail-pages/{id}` | 진행 상황과 결과 |
| | `POST /detail-pages/{id}/sections/{index}` | 한 칸만 다시 만들기 |
| 상담과 조언 | `POST /consults` | AI 광고 상담 시작 |
| | `POST /consults/{id}/messages` | 상담 답변 보내기 |
| | `GET /consults/{id}` | 상담 내용과 기획서 |
| | `POST /advice` | Terra 광고 조언 (자유 대화) |
| | `GET /tips` | 생성 대기 중 보여 줄 팁 카드 |
| 운영 | `POST /events` | 사용자 행동 기록 |
| | `GET /stats` | p50, p95 시간, 비용, 오류율 통계 |
| | `GET /health` | 모델 준비 상태와 웜업 결과 |

## 이미지 생성 경로

| 경로 | 언제 | 모델 |
|---|---|---|
| 기본 (primary) | 빠르게를 골랐을 때 | 로컬 klein, 대기열 1개 |
| 프리미엄 (premium) | 더 정교하게를 골랐을 때 | flare, 대기열 없이 바로 |
| 폴백 (대기) | 예상 완료 시간이 `max_wait_seconds`보다 길 때 | flare |
| 폴백 (미준비) | 로컬 모델 준비 실패 | flare |
| 폴백 (장애) | 재시도 후에도 실패하거나 제한 시간 초과 | flare |

폴백과 프리미엄은 하루 `extra_daily_limit`까지만 쓰고, 넘으면 기본 대기열로 보냅니다.

## 운영 장치

| 장치 | 하는 일 | 기본값 |
|---|---|---|
| 대기열 | 로컬 klein은 한 번에 1건 | 큐 50건, 재시도 1회 |
| 대기 폴백 | 대기가 길면 OpenAI로 넘김 | 30초 |
| 제한 시간 | 시간이 지나면 core의 모델 호출까지 멈춤 (`core/deadline.py`) | 생성 90초, 문구 60초, 동기 응답 110초 |
| 비용 상한 | 하루 쓴 금액이 넘으면 유료 호출 차단, 상담은 예산 일부만 | 하루 $3, 상담 33% |
| 하루 한도 | 서비스 전체와 사용자, IP별 횟수 | 생성 300건, 상담과 조언 사용자 3회, IP 10회 |
| 입력 검사 | 사진 크기, 글자 수 | 10MB, 문구 200자, 상품명 50자 |
| 모더레이션 | 상담과 조언에서 사장님이 직접 쓴 글만 검사 | OpenAI Moderation (무료) |
| 웜업 | 서버가 켜질 때 klein을 미리 불러옴 (`core.pipeline.warmup`) | 켜짐 |

동기 응답 제한(110초)은 Vercel 프록시가 120초에 연결을 끊는 것에 맞춘 값입니다.

## 폴더 구조

```
📦 serving
┣ 📂 generators         # 이미지 생성기
┃ ┣ 📄 base.py          # 생성기 공통 형식
┃ ┣ 📄 core_adapter.py  # core 파이프라인 연결
┃ ┗ 📄 mock.py          # GPU, API 키 없이 쓰는 가짜 생성기
┣ 📄 __init__.py
┣ 📄 main.py            # FastAPI 실행, 모델 로딩과 웜업
┣ 📄 router.py          # 엔드포인트
┣ 📄 schemas.py         # 요청, 응답 형식
┣ 📄 settings.py        # 서빙 설정값 (.env로 변경 가능)
┣ 📄 queue_manager.py   # 작업 큐, 폴백 경로, 제한 시간, 생성 로그
┣ 📄 records.py         # 생성 기록과 이미지 저장
┣ 📄 assistant.py       # 상담, 조언, 게시 문구 변환
┣ 📄 copywriter.py      # 문구 추천
┣ 📄 detail_pages.py    # 상세페이지 비동기 생성
┣ 📄 gpu_check.py       # klein과 Gemma 동시 탑재 측정
┗ 📝 README.md
```

## 실행

**로컬 개발 (GPU, API 키 없이)**

`.env`에 `IMAGE_BACKEND=mock`을 넣고 실행합니다.

```bash
uv run uvicorn just_make_it.serving.main:app --host 0.0.0.0 --port 8000 --workers 1
```

워커는 반드시 1개로 둡니다. 워커마다 모델을 따로 불러와 VM 메모리(16GB)가 부족해지기 때문입니다.

**VM 배포 (Docker)**

```bash
docker compose up -d --build
```

- `api`: 서빙 서버 (GPU 1장)
- `ollama`: Gemma 4 12B
- `ollama-pull`: Gemma 가중치를 처음 한 번 받는 작업

이미지 크기와 배포 시간 정리는 [`docs/serving/docker_build.md`](../../../docs/serving/docker_build.md)에 있습니다.

**GPU 사용량 측정**

```bash
docker compose stop api
docker compose run --rm --no-deps api python -m just_make_it.serving.gpu_check
docker compose start api
```

## 주요 설정값 (.env)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `IMAGE_BACKEND` | `core` | `mock`이면 가짜 생성기 |
| `QUEUE_FALLBACK` | `true` | 대기가 길 때 OpenAI로 넘길지 |
| `WARMUP_ON_START` | `true` | 서버 시작 시 klein 웜업 |
| `MAX_WAIT_SECONDS` | `30` | 이 시간보다 오래 기다려야 하면 폴백 |
| `QUEUE_MAX_SIZE` | `50` | 대기열 최대 길이 |
| `DAILY_JOB_LIMIT` | `300` | 하루 전체 생성 수 |
| `EXTRA_DAILY_LIMIT` | `100` | 그중 폴백과 프리미엄 수 |
| `OPENAI_DAILY_BUDGET_USD` | `3.0` | 하루 OpenAI 금액 상한 |
| `CONSULT_BUDGET_SHARE` | `0.33` | 상한 중 상담과 문구에 쓸 비율 |
| `GENERATION_TIMEOUT_SECONDS` | `90` | 생성 1건 제한 시간 |
| `GENERATE_WAIT_SECONDS` | `110` | 동기 생성 응답 제한 시간 |
| `DATA_DIR` | `data` | DB와 생성 이미지 위치 |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | 허용할 프론트 주소 |

모델과 API 키 설정은 core가 쓰는 `config.py`를 따릅니다. [`core/README.md`](../core/README.md)를 참고하세요.

## 테스트

```bash
uv run pytest tests/test_serving.py tests/test_serving_warmup.py tests/test_deadline.py tests/test_budget.py tests/test_detail_pages.py tests/test_text_edit.py
```

Mock 생성기를 쓰기 때문에 GPU나 API 키 없이 실행됩니다.
