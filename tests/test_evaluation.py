"""정량평가 자동 점수(auto_scores)와 리포트(make_report) 테스트.

CLIP, OCR 모델은 불러오지 않고 가짜 채점기로 바꿔 끼웁니다.
"""

import csv
import json

from test_core import fakes  # noqa: F401 (fixture)

from just_make_it.core.evaluation import make_report, run_eval
from just_make_it.core.evaluation.auto_scores import char_match, clip_text, score_row


class FakeScorer:
    def __init__(self):
        self.calls = []

    def clip_score(self, image_bytes, prompt):
        self.calls.append("clip")
        return 0.31

    def ref_similarity(self, image_bytes, reference_bytes):
        self.calls.append("ref")
        return 0.8

    def ocr_match(self, image_bytes, text):
        self.calls.append("ocr")
        return 0.9


class MissingScorer:
    def clip_score(self, *args):
        raise RuntimeError("eval 패키지 없음")


def test_clip_text_keeps_only_description():
    prompt = (
        "Use the product in the reference image as the main subject. "
        "A professional commercial photograph of a golden roll. "
        "Warm light on a wooden table. Mood: warm, cozy. "
        "No text, no letters. Photorealistic, high quality."
    )
    assert clip_text(prompt) == (
        "A professional commercial photograph of a golden roll. "
        "Warm light on a wooden table."
    )


def test_char_match_ignores_spaces_and_marks():
    assert char_match("오늘의 소금빵!", "오늘의소금빵") == 1.0
    assert char_match("오늘의 소금빵", "오늘 소금") == round(4 / 6, 4)
    assert char_match("", "아무거나") is None


def test_score_row_by_output():
    scorer = FakeScorer()
    row = {"output": "combined", "prompt": "A photo.", "overlay_text": "신메뉴"}
    assert score_row(scorer, row, b"img", b"bg", b"ref") == {
        "clip_score": 0.31,
        "ref_similarity": 0.8,
        "ocr_match": 0.9,
    }
    image_only = score_row(FakeScorer(), {**row, "output": "image"}, b"img", b"bg")
    assert image_only == {"clip_score": 0.31, "ref_similarity": "", "ocr_match": ""}
    text_only = score_row(FakeScorer(), {**row, "output": "text"}, None, None)
    assert text_only == {"clip_score": "", "ref_similarity": "", "ocr_match": ""}


def test_fill_scores_skips_when_packages_missing():
    rows = [{"case_id": "C01", "error": "", "prompt": "A photo.", "output": "image"}]
    run_eval.fill_scores(rows, [(b"img", b"bg")], scorer=MissingScorer())
    assert "clip_score" not in rows[0]


def test_run_eval_writes_auto_scores(fakes, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "Scorer", FakeScorer)
    csv_path = run_eval.run_eval("t", reference_image=None)
    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    combined = next(r for r in rows if r["output"] == "combined")
    image_only = next(r for r in rows if r["output"] == "image")
    assert combined["clip_score"] == "0.31" and combined["ocr_match"] == "0.9"
    assert image_only["ocr_match"] == "" and image_only["ref_similarity"] == ""
    assert (
        combined["overlay_text"] and (csv_path.parent / combined["background"]).exists()
    )


def test_summarize_mean_p95_and_rates():
    rows = [
        {
            "error": "",
            "elapsed_sec": str(s),
            "cost_usd": "0.01",
            "clip_score": "0.3",
            "fallback_reason": "klein 실패" if s == 10 else "",
            "model": "klein",
        }
        for s in range(1, 21)
    ] + [{"error": "실패", "elapsed_sec": "", "cost_usd": "", "model": ""}]
    s = make_report.summarize(rows)
    assert (s["generated"], s["errors"]) == (20, 1)
    assert s["elapsed_sec"] == {"mean": 10.5, "p95": 19.0}
    assert s["clip_score"]["mean"] == 0.3 and s["ocr_match"]["mean"] is None
    assert s["cost_per_image_usd"] == 0.01 and s["fallback_rate"] == 0.05


def test_report_has_quantitative_table_and_json(tmp_path, monkeypatch):
    run = tmp_path / "r1"
    run.mkdir()
    with (run / "results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "run_id",
                "case_id",
                "purpose",
                "product_name",
                "message",
                "style",
                "output",
                "model",
                "error",
                "image",
                "prompt",
                "elapsed_sec",
                "cost_usd",
                "clip_score",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "run_id": "r1",
                "case_id": "C01",
                "purpose": "free",
                "product_name": "빵",
                "message": "신메뉴",
                "style": "",
                "output": "image",
                "model": "klein",
                "error": "",
                "image": "images/C01.png",
                "prompt": "p",
                "elapsed_sec": "3",
                "cost_usd": "0",
                "clip_score": "0.3",
            }
        )
    monkeypatch.setattr(make_report, "RESULTS_DIR", tmp_path)
    make_report.main()
    assert "정량평가" in (tmp_path / "report.html").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["r1"]["clip_score"]["mean"] == 0.3
