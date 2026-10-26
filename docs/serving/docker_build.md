# api 이미지 크기·CD 시간 정리 (V5)

2026-10-26 · 서빙(장한빈)

## 결론

| 증상 | 원인 | 고친 것 |
|------|------|---------|
| api 이미지 약 19GB | GPU 의존성 `.venv`(압축 휠 약 3GB, 풀면 수 GB)가 이미지에 **두 벌** 들어감. 런타임 단계 마지막 `chown -R appuser /app`이 `.venv` 전체를 새 레이어로 한 번 더 씀 | `COPY --chown`으로 복사하면서 소유자 지정, `chown -R` 삭제 → `.venv` 한 벌 |
| CD 매번 약 15분 | ① `cd.yml`의 `docker builder prune -f`가 빌드 캐시를 지워 배포마다 torch 등을 다시 받고 설치 ② 코드만 바뀌어도 `.venv` 레이어를 다시 만듦(프로젝트를 `.venv`에 설치 + `chown -R`이 src 복사 뒤에 있음) | ① 7일 넘은 캐시만 지움(`--filter until=168h`) ② 의존성만 설치한 단계(`deps`)에서 `.venv`를 복사하고 코드는 `PYTHONPATH`로 → 코드만 바뀐 배포는 `src` 레이어만 새로 만듦 |
| 빌드 컨텍스트가 큼 | `.dockerignore`가 없어 `.git`, `frontend`, `data`(DB·생성 이미지) 등을 매번 Docker로 보냄 | `.dockerignore` 추가 (Dockerfile은 `pyproject.toml`·`uv.lock`·`README.md`·`src/`만 씀) |

uv 캐시를 빌드 캐시 마운트로 남겨서(`RUN --mount=type=cache`), `uv.lock`이 바뀌는 배포도 이미 받은 휠은 다시 받지 않음.

## GPU 의존성이 큰 이유

`uv.lock` 기준 리눅스 휠(압축) 상위:

| 패키지 | 크기 |
|--------|------|
| torch 2.14.1 | 0.55GB |
| nvidia-cudnn-cu13 | 0.55GB |
| nvidia-cublas | 0.42GB |
| triton | 0.25GB |
| nvidia-nccl-cu13 | 0.22GB |
| nvidia-cufft · cusolver · cusparselt · cusparse 등 | 각 0.15~0.2GB |

PyPI torch 휠은 CUDA 런타임을 nvidia-* 패키지로 같이 받는다. CUDA 베이스 이미지를 쓰지 않는 대신 이 크기가 `.venv`에 들어간다.
nccl(여러 GPU 통신)처럼 우리가 안 쓰는 것도 있지만, torch가 의존성으로 요구해서 빼면 import가 깨질 수 있어 그대로 둔다.

## 배포 후 확인할 것 (VM)

```bash
sudo docker images just-make-it-api          # 크기: 예전 약 19GB → 절반 근처 예상
sudo docker history just-make-it-api | head  # .venv 레이어가 한 번만 있는지
sudo docker system df                        # 빌드 캐시 크기
```

- 첫 배포는 캐시가 없어서 여전히 오래 걸림. **두 번째 배포(코드만 변경)부터** 몇 분 안에 끝나야 정상
- 이 작업 공간에서는 Docker를 돌릴 수 없어 실제 빌드는 VM 배포로 처음 확인함
