"use client";

import { Chip, Notice } from "@/components/ui";
import { compose, FILLS, floodFill, pixelsOf, removeBackground } from "@/lib/cutout";
import { loadImage } from "@/lib/draw";
import { Check, Eraser, Loader2, Paintbrush, RotateCcw, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface Props {
  photoUrl: string;
  name: string;
  onDone: (file: File) => void;
  onCancel: () => void;
}

type Tool = "erase" | "restore";

/** 올린 사진의 배경을 브라우저에서 지우고, 남은 부분을 고친 뒤 단색 배경으로 채움 */
export function CutoutEditor({ photoUrl, name, onDone, onCancel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [pixels, setPixels] = useState<Uint8ClampedArray | null>(null);
  const [first, setFirst] = useState<Uint8ClampedArray | null>(null); // 모델이 처음 만든 마스크
  const [history, setHistory] = useState<Uint8ClampedArray[]>([]); // 마지막이 지금 마스크
  const [tool, setTool] = useState<Tool>("erase");
  const [fill, setFill] = useState<string>(FILLS[0].color);
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState("");
  const mask = history.at(-1);

  useEffect(() => {
    let alive = true;
    (async () => {
      const image = await loadImage(photoUrl);
      const alpha = await removeBackground(image, (p) => alive && setPercent(p));
      if (!alive) return;
      setImg(image);
      setPixels(pixelsOf(image));
      setFirst(alpha);
      setHistory([alpha]);
    })().catch((e) => {
      console.warn("배경 지우기 실패", e);
      if (alive) setError("이 기기에서는 배경 지우기가 어려워요. 원래 사진으로 만들 수 있어요.");
    });
    return () => {
      alive = false;
    };
  }, [photoUrl]);

  useEffect(() => {
    if (img && mask && canvasRef.current) compose(canvasRef.current, img, mask, fill);
  }, [img, mask, fill]);

  function pick(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!img || !pixels || !mask) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.floor(((e.clientX - r.left) / r.width) * img.naturalWidth);
    const y = Math.floor(((e.clientY - r.top) / r.height) * img.naturalHeight);
    if (x < 0 || y < 0 || x >= img.naturalWidth || y >= img.naturalHeight) return;
    const next = floodFill(pixels, mask, img.naturalWidth, img.naturalHeight, x, y, tool === "erase" ? 0 : 255);
    setHistory([...history.slice(-9), next]); // ponytail: 되돌리기 10번까지. 마스크가 장당 수 MB라 메모리 보호
  }

  function done() {
    canvasRef.current?.toBlob((blob) => {
      if (!blob) return setError("사진을 만들지 못했어요. 다시 해 주세요.");
      onDone(new File([blob], name.replace(/\.\w+$/, "") + "-배경.png", { type: "image/png" }));
    }, "image/png");
  }

  if (error)
    return (
      <Notice action={<button type="button" className="btn-line min-h-[44px] px-4" onClick={onCancel}>원래 사진 쓰기</button>}>
        {error}
      </Notice>
    );

  if (!mask)
    return (
      <div role="status" aria-live="polite" className="flex flex-col items-center gap-3 rounded-card bg-mist px-6 py-10 text-center">
        <Loader2 aria-hidden className="size-8 animate-spin" />
        <p className="font-semibold">배경을 지우고 있어요</p>
        <p className="hint">
          {percent > 0 && percent < 100 ? `AI 도구 받는 중 ${percent}% (처음 한 번만, 약 115MB)` : "기기에 따라 몇 초에서 30초쯤 걸려요."}
        </p>
      </div>
    );

  return (
    <section className="card flex flex-col gap-6" aria-label="배경 지우기">
      <div className="overflow-hidden rounded-card shadow-sm">
        <canvas
          ref={canvasRef}
          role="img"
          aria-label="배경을 지운 상품 사진 미리보기. 누르면 비슷한 색 영역을 지우거나 되살려요"
          className="block h-auto w-full cursor-crosshair touch-none"
          onPointerDown={pick}
        />
      </div>

      <fieldset>
        <legend className="label">남은 부분 고치기</legend>
        <p className="-mt-1 mb-3 hint">도구를 고르고 사진을 누르면 비슷한 색 영역이 한 번에 바뀌어요.</p>
        <div className="flex flex-wrap gap-2">
          <Chip on={tool === "erase"} onClick={() => setTool("erase")}>
            <Eraser aria-hidden className="size-4" /> 지우개
          </Chip>
          <Chip on={tool === "restore"} onClick={() => setTool("restore")}>
            <Paintbrush aria-hidden className="size-4" /> 되살리기
          </Chip>
          <button type="button" className="chip" disabled={history.length < 2} onClick={() => setHistory(history.slice(0, -1))}>
            <Undo2 aria-hidden className="size-4" /> 되돌리기
          </button>
          <button type="button" className="chip" disabled={history.length < 2} onClick={() => first && setHistory([first])}>
            <RotateCcw aria-hidden className="size-4" /> 처음으로
          </button>
        </div>
      </fieldset>

      <fieldset>
        <legend className="label">배경 색</legend>
        <div className="flex flex-wrap gap-2">
          {FILLS.map((f) => (
            <Chip key={f.id} on={fill === f.color} onClick={() => setFill(f.color)}>
              <span aria-hidden className="size-5 rounded-full border-2 border-ink" style={{ background: f.color }} />
              {f.name}
            </Chip>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <button type="button" className="btn-fill" onClick={done}>
          <Check aria-hidden className="size-5" /> 이 사진으로 쓰기
        </button>
        <button type="button" className="btn-line" onClick={onCancel}>
          원래 사진 그대로 쓰기
        </button>
      </div>
    </section>
  );
}
