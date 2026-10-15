# just make it - AI 광고 이미지 생성 서비스

> **"Just Make It" 팀의 하이브리드 AI 이미지 생성 및 서빙 플랫폼 프로젝트입니다.**
본 프로젝트는 GCP L4 GPU 환경의 가성비와 OpenAI API의 안정성을 결합하여 대규모 트래픽(MAU) 대응이 가능한 이미지 생성 아키텍처를 구축합니다.

---

## 프로젝트 개요 및 핵심 아키텍처

우리의 목표는 **비용 최적화**와 **무중단 서비스 보장**을 동시에 달성하는 것입니다.

*   **기본 라우팅 (로컬 L4 GPU):** 일반적인 이미지 생성 요청은 자체 서빙 모델(SDXL 가속 버전 등)로 처리하여 비용을 `0원`으로 수렴시킵니다.
*   **우회 라우팅 (OpenAI Fallback):** 로컬 GPU 대기 큐(Queue)가 가득 차거나 프리미엄 기능을 요청할 경우, `OpenAI DALL-E 3 API`로 요청을 즉시 우회하여 유저 대기 시간을 최소화합니다.

⚠️ **하드웨어 제약 조건:** GCP g2-standard-4 인스턴스는 **시스템 RAM이 16GB**로 매우 제한적입니다. 모든 파트는 메모리 누수 방지 및 최적화 설정을 최우선으로 고려해야 합니다.

---

## 팀원 역할 및 작업 영역 (Role & Responsibilities)

프로젝트 코드는 각 담당자의 역할에 따라 `src/just_make_it/` 하위 폴더로 격리되어 관리됩니다.

### 1. 📋 PM (Project Manager)
*   **담당 영역:** `README.md`, `docs/` (기획안 및 API 스펙 관리)
*   **핵심 미션:** 제품 스펙 정의, 기능 요구사항 구체화, API 엔드포인트 명세 조율.

### 2. 🧠 모델 개발 (Model Engineer)
*   **담당 영역:** `src/just_make_it/core/`
*   **핵심 미션:** RAM 16GB 환경에서 구동 가능한 경량/가속 이미지 생성 파이프라인(SDXL Lightning, SD 1.5 등) 구축, FP16 양자화 및 VRAM 캐시 최적화.

### 3. 🌐 서빙 엔지니어 (Serving Engineer)
*   **담당 영역:** `src/just_make_it/serving/`
*   **핵심 미션:** FastAPI 기반 인프라 구축, **동시성 제어를 위한 단일 워커(--workers 1)** 세팅, 로컬 GPU 상태 모니터링을 통한 OpenAI 비동기 분기 로직(`queue_manager.py`) 구현.

### 4. 🛠️ 서비스 개발 (Backend Developer)
*   **담당 영역:** `src/just_make_it/service/`
*   **핵심 미션:** 비즈니스 로직 구현, 유저 인증 및 프리미엄 모드 판별, 생성 완료된 이미지 데이터의 GCP Cloud Storage(GCS) 업로드 및 영구 URL 발급 파이프라인 연동.

---

## 🛠️ 개발 환경 설정 (Local Setup)

본 프로젝트는 초고속 파이썬 패키지 매니저인 `uv`를 사용합니다.

### 1. 전제 조건
*   로컬 환경에 `uv`가 설치되어 있어야 합니다. (설치: `curl -LsSf https://astral.sh | sh`)

### 2. 프로젝트 초기화 및 가상환경 생성
```bash
# 레포지토리 클론 후 이동
git clone git@github.com:sprint-ai-12-4team/just-make-it.git
cd just-make-it

# 파이썬 가상환경 생성 및 의존성 동기화 (.venv 자동 생성)
uv sync
```

### 3. 환경 변수 설정 (`.env`)
프로젝트 루트에 `.env` 파일을 생성하고 아래 키를 입력합니다. (Git에 커밋 금지)
```text
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_APPLICATION_CREDENTIALS=path_to_your_gcp_key.json
```

---

## 🚀 CI/CD 및 배포 파이프라인

`main` 브랜치에 `push` 또는 `PR merge`가 발생하면 GitHub Actions를 통해 GCP L4 인스턴스에 자동 배포됩니다.

*   **배포 방식:** Docker 멀티 스테이지 빌드 기반 컨테이너 배포
*   **실행 옵션:** 시스템 RAM 사수를 위해 인스턴스 내에서 반드시 `--workers 1` 및 `--gpus all` 옵션으로 격리 구동됩니다.
*   **인프라 수칙:** 인스턴스 OS 단계에서 최소 16GB의 Swap Memory가 상시 활성화되어 있어야 합니다.

---

## 🤝 협업 가이드 (Git Branch Strategy)

*   `main`: 프로덕션 배포 브랜치 (직접 푸시 절대 금지)
*   `feature/{role}-{기능명}`: 각 파트별 작업 브랜치
    *   예: `feature/model-sdxl-lightning`
    *   예: `feature/serving-fallback-logic`
    *   예: `feature/service-gcs-upload`
*   **Code Review:** 모든 PR은 담당 파트 외 1명 이상의 리뷰와 승인(Approve)을 거쳐 `main`에 머지됩니다.
*   

---

## 기본 디렉토리
```bash
just-make-it/
├── .github/
│   └── workflows/
│       └── cd.yml               # GitHub Actions CI/CD 스크립트
├── .python-version              # uv가 관리하는 파이썬 버전 (예: 3.11)
├── pyproject.toml               # uv 프로젝트 설정 및 의존성 관리
├── uv.lock                      # uv 패키지 락 파일 (버전 고정)
├── README.md                    # [PM] 프로젝트 기획 및 가이드문서
├── docs/                        # [PM] 기능 명세서, API 스펙 문서
│   └── api_spec.md
├── src/
│   └── just_make_it/        # uv 메인 패키지 root
│       ├── __init__.py
│       ├── config.py            # 환경 변수 및 설정 (OpenAI Key, VRAM 제한 등)
│       │
│       ├── core/                # [모델 개발] 파이프라인 최적화 및 로드 담당
│       │   ├── __init__.py
│       │   ├── loader.py        # SDXL, LoRA 로드 및 RAM 16GB 최적화 옵션 설정
│       │   └── pipeline.py      # local_sd_pipeline 추론 실행 및 VRAM 캐시 비우기
│       │
│       ├── serving/             # [서빙] API 라우팅 및 하이브리드 로직 분기 담당
│       │   ├── __init__.py
│       │   ├── main.py          # FastAPI 실행 엔트리포인트 (Workers=1 설정)
│       │   ├── router.py        # /generate 엔드포인트
│       │   └── queue_manager.py # 로컬 GPU 상태 체크 (is_busy) 및 OpenAI Fallback 제어
│       │
│       └── service/             # [서비스 개발] 백엔드 비즈니스 로직, 외부 연동 담당
│           ├── __init__.py
│           ├── gcs_storage.py   # 생성된 이미지를 Google Cloud Storage에 업로드
│           └── user_auth.py     # 유저 권한 및 프리미엄 모드 체크
└── tests/                       # 테스트 코드 영역
    └── test_serving.py

```