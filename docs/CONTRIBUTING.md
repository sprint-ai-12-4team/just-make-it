# 협업 가이드

## 브랜치

| 브랜치 | 용도 |
|--------|------|
| `main` | 기준 브랜치. 직접 푸시 금지, PR로만 |
| `dev` | 각 파트 통합. 푸시하면 VM에 자동 배포 |
| `feature/{role}-{기능명}` | 작업 브랜치. 예: `feature/model-scene-only`, `feature/serving-fallback-logic`, `feature/svc-fe-qr` |

## 리뷰

- 모든 PR은 담당 파트 외 1명 이상 승인(Approve) 후 머지
- 변경 후 관련 테스트 실행 (`uv run pytest tests/ -v`). Docker를 바꿨으면 `docker compose up --build`로 한 번 확인
- 커밋 메시지: `type: 한국어 설명` (예: `feat: 결과 화면 QR 미리보기`, `docs(api_spec): …`)

## 담당 영역

| 영역 | 담당 | 규칙 |
|------|------|------|
| `README.md`, `docs/`, `CLAUDE.md` | PM | |
| `src/just_make_it/core/` | 모델 | 모델 로드·추론은 여기서만 |
| `src/just_make_it/serving/`, `Dockerfile`, `docker-compose.yml` | 서빙 | 라우팅·대기열·Fallback. 모델 직접 로드 금지 |
| `src/just_make_it/service/`, `frontend/` | 서비스 | 비즈니스 로직, DB, 이미지 저장, 화면 |

담당 밖의 코드는 직접 고치지 않고 담당자에게 요청하거나 PR에서 담당자 승인을 받습니다.

## 지켜야 할 제약

- 비밀값(`OPENAI_API_KEY` 등)은 `.env`에만. 키 목록은 `.env.example`
- 테스트·반복 호출에서 실제 OpenAI API를 남용하지 않음 (팀 한도)
- 모델 가중치는 Docker 이미지에 넣지 않음 (`model-cache` 볼륨)
