"""고정된 테스트 케이스로 광고 이미지를 생성하고 결과를 기록합니다.

같은 test_cases.csv로 설정만 바꿔 돌리면, 결과를 나란히 비교할 수 있습니다.

실행 예시
    python -m just_make_it.core.evaluation.run_eval --tag v1
    python -m just_make_it.core.evaluation.run_eval --tag v1_ref --reference 상품사진.png
    python -m just_make_it.core.evaluation.run_eval --tag v1_api --image-quality detailed --text-quality natural

결과
    src/just_make_it/core/evaluation/results/{실행ID}/images/   생성 이미지
    src/just_make_it/core/evaluation/results/{실행ID}/results.csv   사용 모델, 폴백 여부, 걸린 시간, 정성평가 점수 칸
"""

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from just_make_it.core.base import ImageGenerationError, TextGenerationError
from just_make_it.core.pipeline import generate_ad_image

BASE_DIR = Path(__file__).parent
CASES_PATH = BASE_DIR / "test_cases.csv"
RESULTS_DIR = BASE_DIR / "results"
KST = timezone(timedelta(hours=9))

SCORE_COLUMNS = [
    "score_prompt",
    "score_quality",
    "score_text",
    "score_usable",
    "comment",
]


def load_cases(path):
    """테스트 케이스 CSV를 읽어옵니다.

    Args:
        path: test_cases.csv 경로

    Returns:
        list: 케이스 목록
    """
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def run_eval(tag, reference_image=None, image_quality="fast", text_quality="basic"):
    """모든 케이스를 생성하고 results.csv로 저장합니다.

    한 케이스가 실패해도 멈추지 않고 error 칸에 기록한 뒤 다음 케이스로 넘어갑니다.

    Args:
        tag: 실행을 구분할 이름 (예: v1, v1_ref)
        reference_image: 모든 케이스에 같이 넣을 참고 사진 바이트. 없으면 None
        image_quality: fast(klein) 또는 detailed(flare)
        text_quality: basic(Gemma) 또는 natural(luna)

    Returns:
        Path: 저장된 results.csv 경로
    """
    run_id = f"{datetime.now(KST):%Y%m%d_%H%M}_{tag}"
    image_dir = RESULTS_DIR / run_id / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    cases = load_cases(CASES_PATH)
    for i, case in enumerate(cases, 1):
        row = {"run_id": run_id, **case}
        try:
            result = generate_ad_image(
                product_name=case["product_name"],
                message=case["message"],
                purpose=case["purpose"],
                style=case["style"] or None,
                output=case["output"],
                reference_image=reference_image,
                image_quality=image_quality,
                text_quality=text_quality,
            )
            image_name = f"{case['case_id']}.png"
            (image_dir / image_name).write_bytes(
                result.image_bytes or result.text_layer_bytes
            )
            row.update(
                model=result.image_model,
                fallback_reason=result.image_fallback_reason,
                text_model=result.text_model,
                text_fallback_reason=result.text_fallback_reason,
                product_source=result.product_source,
                elapsed_sec=result.elapsed_sec,
                cost_usd=result.cost_usd,
                seed=result.seed,
                image=f"images/{image_name}",
                prompt=result.prompt,
                error="",
            )
        except (ImageGenerationError, TextGenerationError, ValueError) as e:
            row.update(
                model="",
                fallback_reason="",
                text_model="",
                text_fallback_reason="",
                product_source="",
                elapsed_sec="",
                cost_usd="",
                seed="",
                image="",
                prompt="",
                error=str(e),
            )

        row.update({col: "" for col in SCORE_COLUMNS})
        rows.append(row)
        print(
            f"[{i}/{len(cases)}] {case['case_id']} {'실패' if row['error'] else '완료'}"
        )

    csv_path = RESULTS_DIR / run_id / "results.csv"
    # 엑셀에서 한글이 깨지지 않게 utf-8-sig로 저장
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def main():
    """명령행 인자를 받아 평가를 실행합니다."""
    parser = argparse.ArgumentParser(description="광고 이미지 정성평가용 일괄 생성")
    parser.add_argument("--tag", default="v1", help="실행 구분 이름 (예: v1, v1_ref)")
    parser.add_argument(
        "--reference", default=None, help="모든 케이스에 넣을 참고 사진 경로 (선택)"
    )
    parser.add_argument(
        "--image-quality",
        default="fast",
        choices=["fast", "detailed"],
        help="그림 품질",
    )
    parser.add_argument(
        "--text-quality",
        default="basic",
        choices=["basic", "natural"],
        help="문구 품질",
    )
    args = parser.parse_args()

    reference = Path(args.reference).read_bytes() if args.reference else None
    csv_path = run_eval(args.tag, reference, args.image_quality, args.text_quality)
    print(f"저장: {csv_path}")
    print("results.csv를 엑셀로 열어 점수 칸을 채운 뒤 make_report.py를 실행하세요.")


if __name__ == "__main__":
    main()
