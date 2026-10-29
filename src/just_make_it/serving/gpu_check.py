"""VM에서 klein과 Gemma를 GPU에 같이 올려 둘 수 있는지 재고, GEMMA_KEEP_ALIVE·타임아웃을 추천한다.

실행 (VM. 서버가 klein을 들고 있으면 두 벌이 올라가 측정이 틀어지므로 api를 잠깐 멈춘다):
    docker compose stop api
    docker compose run --rm --no-deps api python -m just_make_it.serving.gpu_check
    docker compose start api
(ollama 컨테이너는 켜 둔 채로. 걸리는 시간은 klein 첫 다운로드를 빼면 몇 분)

무엇을 재나
1. Gemma 차가운 시작: GPU에서 내린 상태에서 첫 호출 (모델 올리기 + 생성) 시간
2. Gemma 따뜻한 호출: 올라가 있는 상태에서 다시 호출한 시간, Gemma가 차지한 VRAM
3. Gemma를 올려 둔 채로 klein을 불러와 목적별 크기(1024x1024, 1536x864, 1024x1536)로
   생성하면서 GPU 전체 사용량의 최고점 (메모리 부족이면 같이 못 올림)
4. klein이 올라가 있는 상태에서 Gemma를 새로 올릴 때 전부 GPU에 올라가는지
   (Ollama는 자리가 모자라면 일부를 CPU로 내려서 느려짐)

판단
- 3의 최고점 + 여유 1GiB ≤ 전체 VRAM 이고 4에서 Gemma가 전부 GPU에 올라감
  → 같이 올려 둠: GEMMA_KEEP_ALIVE=-1. 느린 건 서버를 띄우고 처음 한 번뿐
- 아니면 → GEMMA_KEEP_ALIVE=0 (쓰고 바로 내림). 이때는 **매 호출이 차가운 시작**이라
  타임아웃을 1의 시간에 맞춰 늘린다

이 스크립트는 Gemma를 GPU에 올렸다 내리고 klein 생성을 여러 번 돌린다. api를 멈춘 동안 서비스는 안 된다.
"""

import json
import math
import sys
import time

import requests

from just_make_it import config

SIZES = [(1024, 1024), (1536, 864), (1024, 1536)]
MARGIN_GIB = 1.0  # 순간적으로 더 쓰는 메모리(조각화 등)를 위한 여유
GIB = 1024**3
PROMPT = "a freshly baked salt bread roll on a wooden table, soft morning light"
# 서빙 설정 이름 (serving/settings.py). 추천값은 측정값에 여유를 곱해 올림한다
SAFETY = 1.5
VERCEL_LIMIT_SECONDS = 120


# ---------------------------------------------------------------------- Ollama
def _ollama(path: str, body: dict | None = None, timeout: float = 300) -> dict:
    url = f"{config.OLLAMA_HOST}{path}"
    if body is None:
        response = requests.get(url, timeout=timeout)
    else:
        response = requests.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    return response.json()


def unload_gemma() -> None:
    """Gemma를 GPU에서 내린다 (keep_alive 0으로 빈 요청)."""
    _ollama("/api/generate", {"model": config.GEMMA_MODEL, "keep_alive": 0})
    time.sleep(2)


def gemma_on_gpu() -> dict:
    """Ollama가 올려 둔 Gemma의 전체 크기와 그중 GPU에 올라간 크기(GiB)."""
    for model in _ollama("/api/ps").get("models", []):
        if model.get("name", "").startswith(config.GEMMA_MODEL):
            return {
                "size_gib": model.get("size", 0) / GIB,
                "vram_gib": model.get("size_vram", 0) / GIB,
            }
    return {"size_gib": 0.0, "vram_gib": 0.0}


def time_gemma(keep_alive) -> float:
    """문구 3개 추천과 비슷한 호출 한 번에 걸린 시간(초)."""
    from just_make_it.core.ai_models.gemma import GemmaTextModel

    config.GEMMA_KEEP_ALIVE = str(keep_alive)
    start = time.perf_counter()
    GemmaTextModel(timeout=600).generate(
        "너는 소상공인 광고 문구를 쓰는 카피라이터야. 문구만 한 줄에 하나씩 3개 써.",
        "상품: 소금빵 / 메시지: 신메뉴 출시 / 분위기: 따뜻한",
    )
    return time.perf_counter() - start


# ---------------------------------------------------------------------- GPU
def gpu_used_gib(torch) -> tuple[float, float]:
    """(GPU 전체 사용량, 전체 VRAM) GiB. 다른 프로세스(Ollama)까지 포함."""
    free, total = torch.cuda.mem_get_info()
    return (total - free) / GIB, total / GIB


def klein_peaks(torch, klein) -> list[dict]:
    """목적별 크기로 klein을 돌리며 GPU 전체 사용량의 최고점을 잰다."""
    results = []
    for width, height in SIZES:
        used, _ = gpu_used_gib(torch)
        others = used - torch.cuda.memory_reserved() / GIB  # Ollama 등 이 프로세스 밖
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        try:
            klein.generate(PROMPT, width, height, seed=1)
            error = ""
        except Exception as exc:  # 메모리 부족이면 같이 못 올리는 것
            error = str(exc)[:200]
        seconds = time.perf_counter() - start
        peak = others + torch.cuda.max_memory_reserved() / GIB
        results.append(
            {
                "size": f"{width}x{height}",
                "seconds": round(seconds, 1),
                "peak_gib": round(peak, 2),
                "error": error,
            }
        )
    return results


# ---------------------------------------------------------------------- 판단
def recommend(m: dict) -> dict:
    """측정값으로 GEMMA_KEEP_ALIVE와 타임아웃을 정한다 (GPU 없이 테스트할 수 있게 분리)."""
    total = m["total_gib"]
    peak = max(r["peak_gib"] for r in m["klein_with_gemma"])
    failed = any(r["error"] for r in m["klein_with_gemma"])
    gemma_full = m["gemma_after_klein"]["vram_gib"] >= m["gemma_after_klein"][
        "size_gib"
    ] - 0.1 and (m["gemma_after_klein"]["size_gib"] > 0)
    fits = not failed and peak + MARGIN_GIB <= total and gemma_full

    klein_max = max(r["seconds"] for r in m["klein_with_gemma"])
    # 같이 못 올리면 Gemma는 매번 차갑게 시작한다
    gemma = m["gemma_warm_sec"] if fits else m["gemma_cold_sec"]
    # 상세페이지 문구 5칸은 문구 3개보다 약 3배 길다
    detail_gemma = (m["gemma_cold_sec"] if not fits else 0) + 3 * m["gemma_warm_sec"]

    def up(seconds: float, floor: float) -> int:
        return max(int(floor), int(math.ceil(seconds * SAFETY / 10) * 10))

    generation = up(gemma + klein_max, 90)
    result = {
        "fits_together": fits,
        "peak_gib": round(peak, 2),
        "total_gib": round(total, 2),
        "reason": (
            "Gemma를 올려 둔 채 klein 최고점 + 여유 1GiB가 VRAM 안에 들어감"
            if fits
            else "같이 올리면 메모리가 모자람"
            + (" (klein 생성 실패)" if failed else "")
            + ("" if gemma_full else " (klein이 있으면 Gemma 일부가 CPU로 내려감)")
        ),
        "env": {
            "GEMMA_KEEP_ALIVE": "-1" if fits else "0",
            "COPY_TIMEOUT_SECONDS": up(gemma, 60),
            "DETAIL_TEXT_TIMEOUT_SECONDS": up(detail_gemma, 90),
            "GENERATION_TIMEOUT_SECONDS": generation,
        },
        "warnings": [],
    }
    # /generate는 대기 + 생성을 GENERATE_WAIT_SECONDS(기본 110) 안에 끝내야 하고
    # Vercel 프록시가 120초에서 끊는다
    if generation >= VERCEL_LIMIT_SECONDS - 10:
        result["warnings"].append(
            f"생성 1건이 {generation}초까지 걸릴 수 있어 Vercel 120초 한도에 걸림. "
            "/generate 첫 요청이 503이 될 수 있음 → klein·Gemma 순서 직렬화나 "
            "Gemma 상주(VRAM 확보)를 검토"
        )
    if not fits:
        result["warnings"].append(
            "같이 못 올리는 상태에서 /copies·상세페이지 문구(Gemma)가 klein 생성과 동시에 "
            "돌면 klein이 메모리 부족으로 실패해 flare(비용)로 넘어갈 수 있음 → "
            "Gemma와 klein을 한 줄로 세우는 GPU 잠금 검토"
        )
    return result


def main() -> int:
    import torch

    from just_make_it.core import ai_models

    if not torch.cuda.is_available():
        print("GPU를 찾을 수 없습니다. VM의 api 컨테이너 안에서 실행하세요.")
        return 1

    m: dict = {"gemma_model": config.GEMMA_MODEL}
    print(f"[1/4] Gemma 차가운 시작 ({config.GEMMA_MODEL})")
    unload_gemma()
    m["baseline_gib"], m["total_gib"] = gpu_used_gib(torch)
    m["gemma_cold_sec"] = round(time_gemma("10m"), 1)

    print("[2/4] Gemma 따뜻한 호출")
    m["gemma_warm_sec"] = round(time_gemma("10m"), 1)
    m["gemma_alone"] = gemma_on_gpu()

    print("[3/4] Gemma를 올려 둔 채 klein 생성 (목적별 크기)")
    klein = ai_models.get_klein()
    m["klein_loaded_gib"] = round(gpu_used_gib(torch)[0], 2)
    m["klein_with_gemma"] = klein_peaks(torch, klein)

    print("[4/4] klein이 올라간 상태에서 Gemma 새로 올리기")
    unload_gemma()
    m["gemma_cold_with_klein_sec"] = round(time_gemma("10m"), 1)
    m["gemma_after_klein"] = gemma_on_gpu()
    unload_gemma()

    result = recommend(m)
    print(
        json.dumps(
            {"measured": m, "recommendation": result}, ensure_ascii=False, indent=2
        )
    )
    print("\n.env에 넣을 값:")
    for key, value in result["env"].items():
        print(f"{key}={value}")
    for warning in result["warnings"]:
        print(f"주의: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
