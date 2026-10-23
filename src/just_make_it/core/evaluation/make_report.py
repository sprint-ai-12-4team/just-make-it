"""results 폴더의 모든 실행 결과를 모아 비교용 HTML 리포트를 만듭니다.

실행: python -m just_make_it.core.evaluation.make_report
결과: src/just_make_it/core/evaluation/results/report.html (브라우저로 열기)
"""

import csv
import html
from collections import Counter
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
SCORE_NAMES = {
    "score_prompt": "프롬프트 반영",
    "score_quality": "이미지 품질",
    "score_text": "문구 디자인",
    "score_usable": "광고 활용성",
}


def load_runs():
    """실행별 results.csv를 모두 읽어옵니다.

    Returns:
        dict[str, list[dict]]: 실행ID별 결과 목록
    """
    runs = {}
    for csv_path in sorted(RESULTS_DIR.glob("*/results.csv")):
        with csv_path.open(encoding="utf-8-sig") as f:
            runs[csv_path.parent.name] = list(csv.DictReader(f))
    return runs


def _numbers(rows, column):
    """빈칸과 숫자가 아닌 값을 뺀 숫자 목록."""
    values = []
    for r in rows:
        try:
            values.append(float(r.get(column, "")))
        except (TypeError, ValueError):
            continue
    return values


def total(rows, column):
    """숫자 칸의 합계. 값이 없으면 -"""
    values = _numbers(rows, column)
    return f"{sum(values):.4f}" if values else "-"


def average(rows, column):
    """빈칸과 숫자가 아닌 값을 빼고 평균을 계산합니다.

    엑셀에서 4점처럼 글자를 섞어 적어도 리포트가 멈추지 않게 숫자만 골라냅니다.

    Args:
        rows: 결과 목록
        column: 평균 낼 칸 이름

    Returns:
        str: 소수점 둘째 자리 평균, 값이 없으면 -
    """
    values = _numbers(rows, column)
    return f"{sum(values) / len(values):.2f}" if values else "-"


def build_report(runs):
    """요약표와 케이스별 이미지 비교표를 HTML로 만듭니다.

    Args:
        runs: 실행ID별 결과 목록

    Returns:
        str: HTML 문서
    """
    esc = html.escape
    head = "".join(f"<th>{name}</th>" for name in SCORE_NAMES.values())
    summary = [
        (
            "<tr><th>실행</th><th>사용 모델(장)</th><th>평균 시간(초)</th>"
            f"<th>총 비용($)</th>{head}<th>실패</th></tr>"
        )
    ]
    for run_id, rows in runs.items():
        scores = "".join(f"<td>{average(rows, col)}</td>" for col in SCORE_NAMES)
        errors = sum(1 for r in rows if r["error"])
        counts = Counter(r.get("model") for r in rows if r.get("model"))
        models = esc(", ".join(f"{m} {n}" for m, n in counts.items()) or "-")
        summary.append(
            f"<tr><td>{esc(run_id)}</td><td>{models}</td>"
            f"<td>{average(rows, 'elapsed_sec')}</td><td>{total(rows, 'cost_usd')}</td>"
            f"{scores}<td>{errors}</td></tr>"
        )

    cases = {}
    for run_id, rows in runs.items():
        for r in rows:
            cases.setdefault(r["case_id"], {})[run_id] = r

    sections = []
    for case_id, by_run in cases.items():
        first = next(iter(by_run.values()))
        title = (
            f"{case_id} | {first['purpose']} | {first['product_name']} | "
            f"{first['message']} | {first['style']} | {first.get('output', '')}"
        )
        cells = []
        for run_id in runs:
            r = by_run.get(run_id)
            if not r:
                cells.append("<td>-</td>")
                continue
            if r["error"]:
                body = f"<p class='err'>실패: {esc(r['error'])}</p>"
            else:
                body = f"<img src='{esc(run_id)}/{esc(r['image'])}'>"
            scores = " / ".join(
                f"{SCORE_NAMES[c]} {r.get(c) or '-'}" for c in SCORE_NAMES
            )
            cells.append(
                f"<td><b>{esc(run_id)}</b>{body}<p>{scores}</p>"
                f"<p>{esc(r.get('comment', ''))}</p>"
                f"<p>{esc(r.get('model', ''))} {esc(r.get('fallback_reason', ''))}</p>"
                f"<p>{esc(r.get('text_model', ''))} {esc(r.get('text_fallback_reason', ''))}</p>"
                f"<details><summary>프롬프트</summary>{esc(r['prompt'])}</details></td>"
            )
        sections.append(
            f"<h3>{esc(title)}</h3><table><tr>{''.join(cells)}</tr></table>"
        )

    style = (
        "body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;margin-bottom:16px}"
        "td,th{border:1px solid #ccc;padding:8px;vertical-align:top;font-size:13px}"
        "td{width:320px}img{width:300px;display:block;margin:6px 0}.err{color:#c00}"
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>{style}</style></head><body>"
        f"<h1>광고 이미지 정성평가 리포트</h1><h2>요약</h2><table>{''.join(summary)}</table>"
        f"<h2>케이스별 비교</h2>{''.join(sections)}</body></html>"
    )


def main():
    """리포트를 만들어 저장합니다."""
    runs = load_runs()
    if not runs:
        print("results 폴더에 실행 결과가 없습니다. run_eval.py를 먼저 실행하세요.")
        return
    report_path = RESULTS_DIR / "report.html"
    report_path.write_text(build_report(runs), encoding="utf-8")
    print(f"저장: {report_path}")


if __name__ == "__main__":
    main()
