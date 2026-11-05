# 정량평가 요청사항 (11-05)

발표 "정량평가" 장표용. FE 페이지 `/stats`(숨김)는 새 칸을 모두 optional로 읽으므로 항목별로 나눠 올려도 됩니다. 값이 없으면 "-"로 보임.

## 서빙

| # | 할 일 | 완료 기준 |
|---|-------|-----------|
| S1 | `POST /advice` 라우트, core `advisor.advise` 연결 ([api_spec.md `POST /advice`](api_spec.md)) | 스펙대로 응답, 실패 시 FE가 기본 안내로 대체할 수 있는 4xx/5xx |
| S2 | `reference_source`(`upload`/`stock`/`null`) 저장(`input_json`)·조회 응답 ([api_spec.md `reference_source`](api_spec.md)) | `GET /generations/{id}`에 값이 보임, 사진 없음·예전 행은 `null` (`/stats`에서는 `none`으로 묶음) |
| S3 | `GET /stats` 추가 칸 ([api_spec.md `/stats 정량평가 추가 칸`](api_spec.md)) | `seconds_p50/p95`, `local_rate`, `cost_usd`, `cost_per_image_usd`, `error_rate`, `by_reference` 반환. 계산 못 하는 값은 `null`, `mock` 결과는 집계 제외 |

## 모델

비교 실행 `v1`(사진 없음) · `v1_ref`(사진 있음) · `v1_api`(OpenAI), 같은 13개 케이스(`core/evaluation/test_cases.csv`).

| # | 할 일 | 완료 기준 |
|---|-------|-----------|
| M1 | `run_eval.py` `results.csv`에 `clip_score` (프롬프트-그림) | 세 실행 모두 값이 있음 |
| M2 | `ref_similarity` (참고 사진-결과) | 사진 있는 실행(`v1_ref`)만 채움, 나머지는 빈 칸 |
| M3 | `ocr_match` (얹은 문구 OCR 일치율) | `combined` 결과만 채움 |
| M4 | `make_report.py`가 `results/summary.json`도 씀 (실행 폴더당 1건) | 아래 모양과 같음. PM이 `frontend/public/eval/summary.json`로 복사 |

```json
{"generated_at": "2026-11-05T12:00:00", "runs": [
  {"run_id": "v1", "cases": 13, "avg_seconds": 9.8, "p95_seconds": 14.1, "cost_usd": 0,
   "fallback_rate": 0, "clip_score": 0.31, "ref_similarity": null, "ocr_match": 0.92}]}
```

숫자는 `null` 가능. 채점은 평가할 때만 CPU로 돌리고(CLIP·OCR), 서빙 이미지·VRAM에는 넣지 않음. 채점에 OpenAI는 쓰지 않음.
