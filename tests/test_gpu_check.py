"""gpu_check의 판단 규칙 테스트 (측정은 VM에서만 가능해서 판단 함수만 검사한다)."""

from just_make_it.serving.gpu_check import recommend


def measured(peak=20.0, total=23.0, error="", gemma_vram=8.5, cold=30.0, warm=3.0):
    return {
        "total_gib": total,
        "gemma_cold_sec": cold,
        "gemma_warm_sec": warm,
        "klein_with_gemma": [
            {"size": "1024x1024", "seconds": 6.0, "peak_gib": peak - 1, "error": ""},
            {"size": "1536x864", "seconds": 7.0, "peak_gib": peak, "error": error},
        ],
        "gemma_after_klein": {"size_gib": 8.5, "vram_gib": gemma_vram},
    }


def test_fits_keeps_gemma_loaded():
    result = recommend(measured(peak=20.0, total=23.0))
    assert result["fits_together"] is True
    assert result["env"]["GEMMA_KEEP_ALIVE"] == "-1"
    # 상주하면 서버 기본값으로 충분
    assert result["env"]["COPY_TIMEOUT_SECONDS"] == 60
    assert result["env"]["GENERATION_TIMEOUT_SECONDS"] == 90


def test_no_margin_unloads_gemma_and_raises_timeouts():
    result = recommend(measured(peak=22.5, total=23.0, cold=45.0))
    assert result["fits_together"] is False
    assert result["env"]["GEMMA_KEEP_ALIVE"] == "0"
    # 매 호출이 차가운 시작(45초) → 1.5배 여유
    assert result["env"]["COPY_TIMEOUT_SECONDS"] == 70
    assert result["env"]["DETAIL_TEXT_TIMEOUT_SECONDS"] == 90
    assert result["env"]["GENERATION_TIMEOUT_SECONDS"] == 90
    assert any("GPU 잠금" in w for w in result["warnings"])


def test_klein_oom_means_not_together():
    result = recommend(measured(error="CUDA out of memory"))
    assert result["fits_together"] is False
    assert "klein 생성 실패" in result["reason"]


def test_gemma_spilling_to_cpu_means_not_together():
    result = recommend(measured(gemma_vram=6.0))
    assert result["fits_together"] is False
    assert "CPU" in result["reason"]


def test_slow_cold_start_warns_about_vercel_limit():
    result = recommend(measured(peak=22.5, cold=80.0))
    assert result["env"]["GENERATION_TIMEOUT_SECONDS"] >= 110
    assert any("Vercel" in w for w in result["warnings"])
