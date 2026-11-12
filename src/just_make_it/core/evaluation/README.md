# evaluation — 정량평가

같은 테스트 케이스로 설정만 바꿔 광고를 만들고, 결과를 자동 점수와 사람 점수로 비교하는 도구입니다. 평가 때만 쓰고 서빙에는 들어가지 않습니다.

## 구성

```
📦 evaluation
┣ 📊 test_cases.csv  # 고정 테스트 케이스 12개
┣ 📄 run_eval.py     # 일괄 생성과 기록
┣ 📄 auto_scores.py  # CLIP, OCR 자동 점수
┣ 📄 make_report.py  # 비교 리포트 생성
┣ 📝 README.md
┗ 📂 results         # 실행 결과 (이미지는 git 제외)
```

## 테스트 케이스

목적 5종(instagram, commerce, youtube, kakao, free), 분위기 5종, 받는 형태 2종(combined, image)이 고르게 섞이도록 12개를 골랐습니다.

| 예시 | 목적 | 상품 | 메시지 | 분위기 |
|---|---|---|---|---|
| C01 | instagram | 소금빵 | 신메뉴 출시 | 따뜻한 |
| C05 | youtube | 떡볶이 | 매운맛 신메뉴 도전 | 강렬한 |
| C10 | free | 카페 | 오픈 기념 아메리카노 50% 할인 | 따뜻한 |

## 설치

채점 모델(CLIP, EasyOCR)은 `eval` 묶음에 있습니다. 서빙 이미지에는 들어가지 않습니다.

```bash
uv sync --extra gpu --extra eval
```

## 실행

**1. 생성과 자동 채점**

```bash
# 기본 설정 (klein + Gemma)
python -m just_make_it.core.evaluation.run_eval --tag v1

# 참고 사진을 넣어서
python -m just_make_it.core.evaluation.run_eval --tag v1_ref --reference 상품사진.png

# API 모델 (flare + luna)
python -m just_make_it.core.evaluation.run_eval --tag v1_api --image-quality detailed --text-quality natural
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--tag` | `v1` | 실행 구분 이름 |
| `--reference` | 없음 | 모든 케이스에 넣을 참고 사진 |
| `--image-quality` | `fast` | `fast`(klein) 또는 `detailed`(flare) |
| `--text-quality` | `basic` | `basic`(Gemma) 또는 `natural`(luna) |
| `--no-scores` | | 자동 점수를 건너뜀 |

**2. 사람 점수 채우기**

`results.csv`를 엑셀로 열어 정성평가 칸을 채웁니다.

**3. 리포트 만들기**

```bash
python -m just_make_it.core.evaluation.make_report
```

## 결과 파일

```
📦 evaluation/results
┣ 📂 {실행ID}
┃ ┣ 📂 images          # 생성 이미지 (_bg는 글자 없는 그림, git 제외)
┃ ┗ 📊 results.csv     # 모델, 폴백 여부, 시간, 비용, 점수
┣ 📄 report.html       # 브라우저로 여는 실행별 비교표
┗ 📄 report.json       # 실행별 요약 숫자
```

## 자동 점수

생성이 끝난 뒤 CLIP과 OCR을 CPU로 불러와 채웁니다. 모두 높을수록 좋습니다.

| 칸 | 뜻 | 계산 방법 |
|---|---|---|
| `clip_score` | 그림이 프롬프트 묘사와 얼마나 맞는지 | 영어 묘사와 글자 없는 그림의 CLIP 유사도 |
| `ref_similarity` | 그림이 참고 사진과 얼마나 닮았는지 | 참고 사진과 글자 없는 그림의 CLIP 유사도 |
| `ocr_match` | 얹은 문구가 제대로 읽히는지 | 문구를 OCR로 다시 읽어 맞은 글자 비율 (combined만) |

- CLIP 유사도는 보통 0.2~0.35 사이라 절대값보다 같은 케이스끼리 실행을 비교할 때 씁니다.
- CLIP은 "No text" 같은 부정문을 이해하지 못해서, 프롬프트에서 지시문은 빼고 상품과 장면 묘사만 넣습니다.
- OCR 비교는 띄어쓰기와 문장부호를 빼고 글자만 봅니다.

## 사람 점수

| 칸 | 기준 |
|---|---|
| `score_prompt` | 프롬프트 반영 |
| `score_quality` | 이미지 품질 |
| `score_text` | 문구 디자인 |
| `score_usable` | 광고 활용성 |
| `comment` | 자유 의견 |

## 리포트 내용

`make_report.py`는 실행마다 아래 숫자를 계산해 한 표로 보여 줍니다. 케이스별 이미지도 실행끼리 나란히 놓아 눈으로 비교할 수 있습니다.

- 자동 점수와 걸린 시간의 평균, p95
- 사람 점수 평균
- 총 비용과 1장당 비용
- 폴백 비율과 사용 모델별 장 수

## 테스트

```bash
uv run pytest tests/test_evaluation.py
```
