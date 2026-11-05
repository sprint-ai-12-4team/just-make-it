"""results 폴더의 모든 실행 결과를 모아 비교용 리포트를 만듭니다.

실행: python -m just_make_it.core.evaluation.make_report
결과
    src/just_make_it/core/evaluation/results/report.html   브라우저로 여는 비교표
    src/just_make_it/core/evaluation/results/report.json   실행별 요약 숫자 (발표 표, 프론트에서 가져다 쓸 때)
"""

import csv
import html
import json
import math
from collections import Counter
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
# 실행별 요약에서 평균과 p95를 내는 자동 숫자 칸
AUTO_NAMES = {
    "clip_score": "CLIP 점수",
    "ref_similarity": "참고 사진 유사도",
    "ocr_match": "OCR 일치율",
    "elapsed_sec": "시간(초)",
}
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


def p95(rows, column):
    """95번째 백분위수 (값을 정렬해 95% 위치의 값). 값이 없으면 -"""
    values = sorted(_numbers(rows, column))
    if not values:
        return "-"
    return f"{values[max(math.ceil(len(values) * 0.95) - 1, 0)]:.2f}"


def summarize(rows):
    """실행 하나의 요약 숫자를 계산합니다.

    Args:
        rows: 결과 목록

    Returns:
        dict: 성공 수, 실패 수, 자동 숫자 칸 평균과 p95, 총 비용, 1장당 비용, 폴백 비율, 사용 모델
    """
    done = [r for r in rows if not r["error"]]
    cost = sum(_numbers(done, "cost_usd"))
    summary = {
        "generated": len(done),
        "errors": len(rows) - len(done),
        "cost_usd": round(cost, 4),
        "cost_per_image_usd": round(cost / len(done), 4) if done else None,
        "fallback_rate": (
            round(sum(1 for r in done if r.get("fallback_reason")) / len(done), 2)
            if done
            else None
        ),
        "models": dict(Counter(r.get("model") for r in done if r.get("model"))),
    }
    for column in AUTO_NAMES:
        mean, top = average(done, column), p95(done, column)
        summary[column] = {
            "mean": None if mean == "-" else float(mean),
            "p95": None if top == "-" else float(top),
        }
    return summary


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

    # 정량평가 표: 자동 숫자 칸의 평균과 p95, 비용, 폴백 비율
    auto_head = "".join(
        f"<th>{name} 평균</th><th>{name} p95</th>" for name in AUTO_NAMES.values()
    )
    quantitative = [
        f"<tr><th>실행</th><th>성공</th>{auto_head}"
        "<th>1장당 비용($)</th><th>폴백 비율</th></tr>"
    ]
    for run_id, rows in runs.items():
        s = summarize(rows)
        cells = "".join(
            f"<td>{_fmt(s[c]['mean'])}</td><td>{_fmt(s[c]['p95'])}</td>"
            for c in AUTO_NAMES
        )
        quantitative.append(
            f"<tr><td>{esc(run_id)}</td><td>{s['generated']}</td>{cells}"
            f"<td>{_fmt(s['cost_per_image_usd'], 4)}</td>"
            f"<td>{_fmt(s['fallback_rate'])}</td></tr>"
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
            autos = " / ".join(
                f"{AUTO_NAMES[c]} {r.get(c) or '-'}"
                for c in AUTO_NAMES
                if c != "elapsed_sec"
            )
            cells.append(
                f"<td><b>{esc(run_id)}</b>{body}<p>{esc(autos)}</p><p>{scores}</p>"
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
        f"<h1>광고 이미지 평가 리포트</h1><h2>요약</h2><table>{''.join(summary)}</table>"
        f"<h2>정량평가</h2><table>{''.join(quantitative)}</table>"
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
    json_path = RESULTS_DIR / "report.json"
    json_path.write_text(
        json.dumps(
            {run_id: summarize(rows) for run_id, rows in runs.items()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"저장: {report_path}, {json_path}")


def _fmt(value, digits=2):
    return "-" if value is None else f"{value:.{digits}f}"


if __name__ == "__main__":
    main()
