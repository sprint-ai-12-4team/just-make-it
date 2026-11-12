# core — 모델 파트

광고 이미지와 문구를 만드는 층입니다. 서빙은 이 폴더의 함수만 부르고, 어떤 모델을 쓸지, 실패하면 어디로 넘길지는 core가 정합니다.

## 서빙에서 쓰는 함수

| 함수 | 하는 일 | 모델 호출 |
|---|---|---|
| `generate_ad_image` | 광고 이미지 생성. 참고 사진은 선택 | 텍스트 + 이미지 |
| `suggest_ad_copies` | 광고 문구 3개 추천 | 텍스트 |
| `render_text` | 글자 고치기. 글자 없는 원본에 문구, 위치, 글꼴, 크기만 바꿔 다시 얹음 | 없음 |
| `suggest_detail_sections` | 상세페이지 5칸 문구 (제목, 설명, 사진 장면) | 텍스트 |
| `restyle_text` | AI로 꾸미기. 만든 이미지의 글자를 flare가 장면에 맞게 다시 그림 | flare |

이 밖에 상담(`consultant.py`), 조언 챗봇(`advisor.py`), 게시 문구 변환(`copy_convert.py`)은 서빙의 assistant가 직접 부릅니다.

## 모델

| 역할 | 기본 (VM 로컬) | 고품질 선택 (OpenAI API) |
|---|---|---|
| 이미지 | FLUX.2 [klein] 4B fp8 | gpt-image-2.6-flare |
| 문구 | Gemma 4 12B (Ollama) | gpt-5.6-luna |
| 상담 기획서, 조언 | | gpt-5.6-terra |

사용자가 고르는 품질 값은 다음과 같습니다.

- 그림 `image_quality`: `fast` (빠르게, 기본값) / `detailed` (더 정교하게)
- 문구 `text_quality`: `basic` (기본, 기본값) / `natural` (더 자연스럽게)

## 생성 흐름

`generate_ad_image` 한 번이 아래 순서로 진행됩니다.

1. 입력 검사
2. 텍스트 짧게 칩이 있으면 문구 줄이기
3. 텍스트 모델이 상품과 메시지를 영어 묘사로 바꿈. 품목 사전에 있으면 사전 묘사를 씀
4. 글자 없는 영어 이미지 프롬프트 만들기
5. 고른 품질의 이미지 모델로 생성
6. 분위기에 맞는 디자인으로 문구 레이어를 만들어 이미지에 얹기

이미지 모델은 글자를 그리지 않습니다. 한글이 깨지지 않도록 문구는 항상 `text_overlay.py`가 따로 얹습니다.

## 폴백 규칙

| 상황 | 동작 |
|---|---|
| klein 실패 | flare로 다시 생성 |
| Gemma 실패 | luna로 다시 생성 |
| klein이 모르는 품목 (사전의 `local_ok`가 False)이고 참고 사진 없음 | 처음부터 flare로 생성 |
| 하루 OpenAI 금액 상한 초과 | 서빙이 텍스트 품질을 `basic`(Gemma)으로 바꿔 부름 |

`USE_FALLBACK=false`면 폴백하지 않고 에러를 냅니다.

## 받는 형태

| `output` | 결과 |
|---|---|
| `combined` (기본값) | 문구를 얹은 이미지, 글자 없는 이미지, 문구 레이어 |
| `image` | 글자 없는 이미지만. 추천 글꼴과 위치를 같이 줌 |
| `text` | 디자인된 문구 레이어(투명 PNG)만. 이미지 모델을 부르지 않음 |

`keep_product=True`면 상품 없는 장면만 그리고, 배경을 지운 상품 사진은 프론트가 장면 가운데 아래에 그대로 놓습니다. 상품 모양과 로고가 바뀌지 않게 하려는 기능입니다.

## 폴더 구조

```
📦 core
┣ 📂 ai_models              # 모델 4종
┃ ┣ 📄 __init__.py          # 모델을 한 번만 불러와 재사용
┃ ┣ 📄 klein.py             # FLUX.2 klein 4B, 텍스트 인코더 8비트
┃ ┣ 📄 fp8_loader.py        # klein fp8 본체 불러오기
┃ ┣ 📄 flare.py             # gpt-image-2.6-flare
┃ ┣ 📄 gemma.py             # Gemma 4 12B (Ollama)
┃ ┗ 📄 luna.py              # gpt-5.6-luna
┣ 📂 assets
┃ ┗ 📂 fonts                # 무료 상업용 글꼴 5종 (OFL)
┣ 📂 evaluation             # 정량평가 도구
┃ ┣ 📝 README.md
┃ ┣ 📊 test_cases.csv
┃ ┣ 📄 run_eval.py
┃ ┣ 📄 auto_scores.py
┃ ┗ 📄 make_report.py
┣ 📄 __init__.py            # 서빙에 공개하는 함수 모음
┣ 📄 pipeline.py            # 이미지 생성 파이프라인, 폴백, 웜업
┣ 📄 copywriter.py          # 문구 추천, 문구 줄이기, 영어 묘사
┣ 📄 prompt_builder.py      # 글자 없는 영어 이미지 프롬프트
┣ 📄 product_dictionary.py  # 한국 품목 생김새 사전
┣ 📄 text_overlay.py        # 분위기별 디자인 5종으로 문구 얹기
┣ 📄 restyle.py             # AI로 꾸미기 (flare 글자 다시 그리기)
┣ 📄 detail_writer.py       # 상세페이지 5칸 문구
┣ 📄 consultant.py          # AI 광고 상담과 기획서
┣ 📄 advisor.py             # Terra 광고 조언 챗봇
┣ 📄 copy_convert.py        # 채널별 게시 문구 변환
┣ 📄 structured.py          # JSON 형식 답 받기, Moderation
┣ 📄 deadline.py            # 작업 제한 시간과 취소 신호
┣ 📄 base.py                # 결과 형식과 에러
┗ 📝 README.md
```

## GPU 메모리 최적화

L4 24GB 한 장에 klein과 Gemma를 함께 올리기 위해 두 가지를 적용했습니다.

| 적용 | 효과 |
|---|---|
| klein 본체를 fp8 파일로 불러오기 (`fp8_loader.py`) | 불러오기 54.8초에서 15.3초, 본체 7.2GB에서 3.8GB |
| 텍스트 인코더 8비트 양자화 (bitsandbytes) | 7.5GB에서 4.1GB, Gemma와 함께 약 19.4GB |

VM 시스템 메모리가 16GB라서, fp8 가중치는 원래 크기로 풀지 않고 계산할 때만 되돌려 씁니다.

## 웜업

서버를 켤 때 `pipeline.warmup()`이 klein을 미리 불러와 512x512 이미지 한 장을 만들어 둡니다. 배포 직후 첫 사용자가 모델 불러오기를 기다리지 않게 하려는 목적입니다.

- OpenAI는 부르지 않습니다.
- 실패해도 서버는 그대로 뜨고, 첫 요청 때 다시 불러옵니다.
- `KLEIN_UNLOAD_AFTER_USE=true`면 건너뜁니다.

## 설정값 (.env)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | | OpenAI 키. 코드에 직접 쓰지 않음 |
| `OLLAMA_HOST` | `http://localhost:11434` | Gemma를 띄운 Ollama 주소 |
| `OPENAI_IMAGE_QUALITY` | `medium` | flare 품질 |
| `USE_FALLBACK` | `true` | 로컬 모델 실패 시 API로 넘길지 |
| `GEMMA_KEEP_ALIVE` | `0` | 문구 작업이 끝나면 Gemma를 GPU에서 바로 내림 |
| `KLEIN_TEXT_ENCODER_BITS` | `8` | 텍스트 인코더 비트 수. `16`이면 원본으로 되돌림 |
| `KLEIN_CPU_OFFLOAD` | `false` | 원본(16비트)일 때만 동작 |
| `KLEIN_UNLOAD_AFTER_USE` | `false` | 한 장마다 klein을 내림. 메모리는 비지만 느려짐 |
| `OPENAI_IMAGE_TIMEOUT` | `75` | flare 제한 시간(초) |
| `OPENAI_TEXT_TIMEOUT` | `30` | luna, terra 제한 시간(초) |
| `OPENAI_MAX_RETRIES` | `1` | OpenAI 재시도 횟수 |
| `GEMMA_TIMEOUT` | `60` | Gemma 제한 시간(초) |

모델 호출 제한 시간은 서빙 제한(90초)보다 짧게 두어, 서빙이 포기한 뒤 호출이 뒤에서 계속 돌지 않게 했습니다.

## 설치

GPU 패키지는 `gpu` 묶음으로 따로 관리합니다. 프론트나 서빙만 개발할 때는 받지 않아도 됩니다.

```bash
uv sync --extra gpu
```

## 테스트

```bash
uv run pytest tests/test_core.py tests/test_warmup.py tests/test_scene_only.py tests/test_keep_product.py tests/test_number_guard.py tests/test_advisor.py tests/test_restyle.py
```

테스트는 모델을 실제로 부르지 않아 GPU나 API 키 없이 실행됩니다.
