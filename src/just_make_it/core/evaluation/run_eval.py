"""고정된 테스트 케이스로 광고 이미지를 생성하고 결과를 기록합니다.

같은 test_cases.csv로 모델이나 설정만 바꿔 돌리면, 결과를 나란히 비교할 수 있습니다.

실행 예시
    python -m just_make_it.core.evaluation.run_eval --backend gpt-image-2.5-flare --tag medium
    python -m just_make_it.core.evaluation.run_eval --backend gpt-image-2.5-flare --tag high --quality high

결과
    src/just_make_it/core/evaluation/results/{실행ID}/images/   생성 이미지
    src/just_make_it/core/evaluation/results/{실행ID}/results.csv   프롬프트, 걸린 시간, 정성평가 점수 칸
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path

from just_make_it.core.base import ImageGenerationError
from just_make_it.core.pipeline import generate_ad_image

BASE_DIR = Path(__file__).parent
CASES_PATH = BASE_DIR / "test_cases.csv"
RESULTS_DIR = BASE_DIR / "results"

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
        list[dict]: 케이스 목록
    """
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def run_eval(backend, tag, options):
    """모든 케이스를 생성하고 results.csv로 저장합니다.

    한 케이스가 실패해도 멈추지 않고 error 칸에 기록한 뒤 다음 케이스로 넘어갑니다.

    Args:
        backend: 사용할 모델 이름 (registry.py에 등록된 이름)
        tag: 실행을 구분할 이름 (예: low, steps30)
        options: 모델에 넘길 추가 옵션 (예: quality)

    Returns:
        Path: 저장된 results.csv 경로
    """
    run_id = f"{datetime.now():%Y%m%d_%H%M}_{backend}_{tag}"
    image_dir = RESULTS_DIR / run_id / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    cases = load_cases(CASES_PATH)
    for i, case in enumerate(cases, 1):
        row = {"run_id": run_id, "backend": backend, "options": str(options), **case}
        try:
            result = generate_ad_image(
                product_name=case["product_name"],
                message=case["message"],
                purpose=case["purpose"],
                style=case["style"] or None,
                generation_mode=case["generation_mode"],
                backend=backend,
                **options,
            )
            image_name = f"{case['case_id']}.png"
            (image_dir / image_name).write_bytes(result.image_bytes)
            row.update(
                model=result.model,
                elapsed_sec=result.elapsed_sec,
                image=f"images/{image_name}",
                prompt=result.prompt,
                error="",
            )
        except (ImageGenerationError, ValueError) as e:
            row.update(model="", elapsed_sec="", image="", prompt="", error=str(e))

        row.update({col: "" for col in SCORE_COLUMNS})
        rows.append(row)
        print(
            f"[{i}/{len(cases)}] {case['case_id']} {'실패' if row['error'] else '완료'}"
        )

    csv_path = RESULTS_DIR / run_id / "results.csv"
    # utf-8-sig로 저장해야 엑셀에서 한글이 깨지지 않음
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def main():
    """명령행 인자를 받아 평가를 실행합니다."""
    parser = argparse.ArgumentParser(description="광고 이미지 정성평가용 일괄 생성")
    parser.add_argument(
        "--backend",
        default="gpt-image-2.5-flare",
        help="registry.py에 등록된 모델 이름",
    )
    parser.add_argument(
        "--tag", default="default", help="실행 구분 이름 (예: low, medium)"
    )
    parser.add_argument(
        "--quality", default=None, help="OpenAI 품질 (low, medium, high)"
    )
    args = parser.parse_args()

    options = {"quality": args.quality} if args.quality else {}
    csv_path = run_eval(args.backend, args.tag, options)
    print(f"저장: {csv_path}")
    print("results.csv를 엑셀로 열어 점수 칸을 채운 뒤 make_report.py를 실행하세요.")


if __name__ == "__main__":
    main()
