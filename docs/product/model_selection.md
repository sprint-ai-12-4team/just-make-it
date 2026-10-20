# 로컬 모델 선택 기능 — 후보 & 동시 상주 조합 (회의용)

> 2026-10-20 · PM 초안 · 수치는 공개 자료 기반 **추정**, L4 실측 후 확정
> 전제: L4 **VRAM 24GB** · RAM 16GB · `--workers 1` · GPU는 한 번에 1건 (활성 메모리 ~3GB는 1건분만 확보) · 상업 이용 가능 라이선스만

## 1. 추천 모델 (각 3종)

| 이미지 | 크기 | VRAM (양자화) | 스텝 | L4 예상 | 라이선스 | 한 줄 평 |
|---|---|---|---|---|---|---|
| **FLUX.2 [klein] 4B** | 4B | ~8.5GB (fp8 + Qwen3-4B 인코더) | 4 | 3~6초 | Apache 2.0 | 빠르고 프롬프트를 잘 따름. 기본값 후보 |
| **Z-Image-Turbo** | 6B | ~10.5GB (INT8 + 인코더) | 8 | 8~15초 | Apache 2.0 | 품질·사실감 최상위. "고품질" 후보 |
| **SDXL Lightning** (기존) | 3.5B | ~7GB (fp16) | 4 | 2~4초 | OpenRAIL++ | 가장 가벼움, LoRA 생태계 최대 |

| 텍스트 (문구) | VRAM (Q4) | L4 예상 (문구 3개) | 라이선스 | 한 줄 평 |
|---|---|---|---|---|
| **Gemma 4 12B** | ~7GB (QAT) | 4~6초 | Apache 2.0 | 140+개 언어, 소형 중 품질 최상위 |
| **Qwen3-8B** | ~6GB | 3~5초 | Apache 2.0 | 다국어 강함. thinking 모드 끄고 사용 |
| **Gemma 4 E4B** | ~4.5GB | 2~3초 | Apache 2.0 | 가장 가벼움, 조합 여유용 |

**제외**: FLUX.1 schnell → klein으로 대체 · SD3.5 Medium → 28스텝 이상, 20초 넘게 걸림 · Qwen-Image-2512 → fp8만 20GB라 단독으로만 상주 가능 · FLUX.2 dev / klein 9B / Qwen-Image-2.1 / EXAONE → 비상업 라이선스 · HunyuanImage 3.0 → **라이선스상 한국에서 사용 금지** · Qwen2.5 / Llama 3.1 / Gemma 2 → 구세대

## 2. 동시 상주 가능 조합 (24GB 안에 드는 것만)

| 조합 | 구성 | 합계 (+활성 3GB) | 선택지 | 문구 |
|---|---|---|---|---|
| **① 이미지 2종** ⭐ | klein 4B + Z-Image-Turbo | ~19GB → **~22GB** | 빠르게 / 고품질 | OpenAI Luna |
| **② 이미지 + 텍스트** | Z-Image-Turbo + Gemma 4 12B | ~17.5GB → **~20.5GB** | 고품질 1종 | 로컬 |
| **③ 경량 3종** | klein 4B + SDXL Lightning + Gemma 4 E4B | ~20GB → **~23GB** (빠듯) | 빠르게 2종 | 로컬 |

- ①을 권장하는 이유: OpenAI 예산($30)은 대부분 이미지에서 나가고, 문구 비용은 아주 작음 → VRAM은 이미지 모델에 쓰는 게 이득.
- klein과 Z-Image는 둘 다 Qwen3-4B 인코더를 씀. **같은 가중치면 한 벌만 올려 ~4GB 절약** (확인 필요).
- 상주하지 않은 모델은 UI에서 뺌. 디스크에서 다시 올리면 RAM 16GB 때문에 수십 초~1분 걸림.

## 3. 선택 → 결과 소요 시간 (조합 ①)

| UI 프리셋 (모델명 대신 표시) | 경로 | 예상 |
|---|---|---|
| ⚡ 빠르게 (기본) | klein 4B → 웹에서 문구 얹기 | **~5초** |
| ✨ 고품질 | Z-Image-Turbo → 웹에서 문구 얹기 | **~10~18초** |
| 🔤 글자 포함 / 📷 참고 사진 | OpenAI Image-2.5 Flare | 10~30초 |

- **로컬 모델은 한글 글자를 제대로 못 그림** (Z-Image도 공식 지원은 영어·중국어뿐) → 로컬 모델은 `template`/`canvas` 전용, `quick`은 OpenAI로.
- 대기열 판단 기준은 건수가 아니라 **예상 대기 시간 합계**. 20초를 넘으면 OpenAI로 넘김.

## 4. FastAPI vs ComfyUI → **FastAPI + diffusers 유지**

| | FastAPI + diffusers | ComfyUI |
|---|---|---|
| 모델 추가 | `registry.py`에 1줄 + 클래스 1개 | 워크플로 JSON + 노드 |
| 메모리 | 상주 조합을 직접 통제 | 자동으로 RAM에 내려두는 방식이 16GB에서 Swap 폭주 위험 |
| 운영 | 프로세스 1개, 대기열 1개 | 프로세스 2개, 대기열 이중 관리 |
| LLM | 같은 프로세스에서 실행 | 미지원 |

ComfyUI는 모델 담당이 로컬에서 품질을 비교하는 실험 도구로만 쓰고, ControlNet·인페인팅이 필요해지면 재검토.

## 5. 회의에서 정할 것
- [ ] 조합 ① / ② / ③ 중 선택 (권장 ①)
- [ ] UI에 모델 이름 노출 여부 (권장: 프리셋만 보여주고, 모델명은 "고급"에 접기)
- [ ] 선택한 로컬 모델이 바쁠 때: OpenAI 자동 전환 vs 대기 (권장: 자동 전환)
- [ ] 실측 담당·기한: `run_eval.py`로 시간·품질 측정, `nvidia-smi`로 VRAM 최대치 기록

<sub>출처: [vdf.ai 로컬 이미지 모델 2026](https://vdf.ai/blog/best-local-image-generation-models/) · [botmonster](https://botmonster.com/ai/best-local-image-generation-models-2026/) · [Gemma 4 개요](https://ai.google.dev/gemma/docs/core) · [Gemma 4 VRAM](https://vdf.ai/blog/gemma-4-on-premises-deployment/) · [HF 로컬 LLM 2026](https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally) · [Z-Image-Turbo 텍스트 렌더링](https://www.emergentmind.com/topics/z-image-turbo)</sub>

