# 한국 품목 이미지 검증 계획 — klein 4B가 소금빵을 그릴 수 있나

> 2026-10-20 · PM 초안 · VRAM 수치는 **추정** (L4 실측 후 확정) · 구성안은 `pipeline_options.md`

## 0. 왜 하나
- 로컬 klein 4B로 만들어 보니 **소금빵 같은 한국 품목을 잘 모름** (크루아상·프레첼처럼 나옴)
- 프롬프트에 "Korean style"을 붙이는 건 효과 없음 → 대신 **모델이 아는 말로 생김새를 풀어 쓰기**
  - ❌ `a shop selling '소금빵', Korean style`
  - ✅ `glossy golden-brown butter roll, coarse sea salt flakes on top, flat crispy bottom`
- 구성 B(Gemma 26B + OpenAI 이미지)는 이 문제가 거의 없음. **문제는 구성 A(Gemma 12B + klein 4B)**

## 1. 확인할 질문 2개
1. **묘사를 잘 써주면 klein이 제대로 그리나?** → 안 되면 묘사로는 해결 불가 (참조 이미지·LoRA 검토)
2. **Gemma 12B가 묘사를 정확히 써주나?** → 안 되면 사람이 쓴 **품목 사전**이 필요

## 2. 방법
품목 10개 × 조건 3개 × seed 3개 = **90장**. 각 장을 O / △ / X로 채점

| 조건 | 프롬프트에 넣는 것 |
|---|---|
| ① 이름만 | `소금빵` (지금 방식) |
| ② 사람 묘사 | 아래 표의 영어 묘사 |
| ③ 12B 묘사 | Gemma 12B에게 "이 품목의 생김새를 영어 1~2문장으로" 요청한 결과 |

나머지 조건은 고정: 목적 `instagram`, 분위기 없음, 글자 없음, 같은 seed 3개

## 3. 품목 10개
| # | 업종 | 품목 | 헷갈리는 점 | 사람 묘사 (조건 ②) |
|---|---|---|---|---|
| 1 | 베이커리 | 소금빵 | 크루아상·프레첼 | glossy golden-brown butter roll with a rolled spiral shape, coarse sea salt flakes on top, flat crispy caramelized bottom where butter melted out |
| 2 | 길거리 | 붕어빵 | 독특한 모양 | fish-shaped waffle pastry, golden brown with fish scale pattern, sweet red bean paste filling, cast-iron fish mold |
| 3 | 길거리 | 호떡 | 팬케이크 | flat round pan-fried dough, crispy golden surface, oozing brown sugar syrup with chopped nuts, held in a paper cup |
| 4 | 분식 | 떡볶이 | 떡 모양·소스 | cylindrical white rice cakes in thick glossy red gochujang sauce, fish cake sheets, boiled egg, sliced green onion, in a wide shallow pan |
| 5 | 분식 | 김밥 | **대조군** (잘 알려짐) | seaweed rice roll sliced into rounds, colorful cross-section of yellow pickled radish, spinach, carrot, egg and ham, sesame oil sheen |
| 6 | 한식 | 순대국 | 국물 색·뚝배기 | milky white pork bone soup boiling in a black stone pot (ttukbaegi), slices of Korean blood sausage and pork, green onion, kimchi on the side |
| 7 | 카페 | 크로플 | 와플 | croissant pressed in a waffle iron, flat with grid pattern, flaky caramelized layers, topped with a scoop of vanilla ice cream and syrup |
| 8 | 카페 | 달고나 라떼 | 달고나 개념 | iced milk latte in a clear glass, topped with crushed golden honeycomb toffee pieces |
| 9 | 디저트 | 약과 | 쿠키 | flower-shaped deep-fried honey cookie, dark glossy amber color, ridged scalloped edges, pine nuts on top |
| 10 | 디저트 | 팥빙수 | **대조군** · 토핑 | finely shaved snow-like milk ice in a bowl, sweet red bean topping, small rice cake cubes dusted with roasted soybean powder |

## 4. 결과 보고 정하기
| ① 이름만 | ② 사람 묘사 | ③ 12B 묘사 | 뜻 | 할 일 |
|---|---|---|---|---|
| O | — | — | 원래 앎 | 그대로 |
| X | O | O | 12B가 잘 풀어줌 | 12B 묘사 + 캐시 |
| X | O | X | 12B가 모름 | **품목 사전**에 사람 묘사 등록 |
| X | X | — | klein이 못 그림 | 참조 이미지·LoRA 검토, 또는 이 품목은 OpenAI로 |

👉 예상: 대부분 2·3번째 줄 → **사전(자주 쓰는 품목만) + 12B 보조 + 캐시**로 충분

## 5. 붙일 구조 (검증 통과 시)
```
품목 입력 → 사전에 있음? → 사전 묘사 (12B 안 거침)
          → 없음 → 캐시 확인 → 없으면 12B가 묘사 생성 → 캐시 저장 ("미검수")
```
- 사전은 처음엔 비어 있어도 됨. 위 검증에서 X 나온 품목부터 채움
- 업종은 10개 안팎 × 배경 한 줄 (예: 분식 → `Korean street food stall, stainless steel tray`). "Korean"은 **배경에만**, 음식에는 안 붙임
- 미검수 묘사는 주기적으로 훑어보고 사전에 올림

## 6. 메모리 — L4 한 장(24GB)·RAM 16GB에 다 올라가나
**VRAM은 됨 (빠듯함). RAM은 로딩 방식만 지키면 됨**

| 구성요소 | 정밀도 | VRAM (추정) |
|---|---|---|
| Gemma 4 12B it | 4bit | ~7~8GB |
| Gemma KV 캐시 (짧은 프롬프트) | — | ~1GB |
| klein 4B transformer | FP8 | ~4GB |
| klein 텍스트 인코더 | 4bit~FP8 | ~2.5~4GB |
| VAE + 1024² 추론 | FP16 | ~3~4GB |
| **합계** | | **~18~21GB** / 실사용 ~22GB |

지킬 것
- **미리 양자화된 가중치를 받기** (GGUF, FP8 등). FP16 원본을 받아 RAM에서 양자화하면 16GB 넘어 스왑 → 로딩 수 분
- safetensors를 GPU로 바로 올리기 (CPU RAM에 전체 사본 X)
- vLLM 쓰면 `gpu_memory_utilization`을 **0.35 안팎**으로 (기본 0.9면 klein 자리 없음)
- 1536×864(유튜브)가 제일 위험 → 넘치면 klein 인코더 4bit → 그래도 넘치면 해상도 상한 1024

## 7. 누가 뭘
| 할 일 | 담당 |
|---|---|
| 90장 생성·채점, 12B 묘사 프롬프트 | 모델 |
| L4에서 VRAM·RAM 실측 (위 표 채우기) | 모델 · 서빙 |
| 품목 사전·업종 목록 확정, `api_spec.md`에 `category`·`item` 추가 | PM |
| 묘사 캐시 테이블, 프론트 업종·품목 칩 | 서비스 |
