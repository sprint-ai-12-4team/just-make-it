"use client";

import { Chip, Notice } from "@/components/ui";
import { compose, cutOf, FILLS, floodFill, HOME, pixelsOf, placeMatrix, removeBackground, type Place } from "@/lib/cutout";
import { loadImage } from "@/lib/draw";
import { drawText, loadFont, TEXT_STYLES, type TextState } from "@/lib/textStyles";
import { Check, Eraser, FlipHorizontal2, FlipVertical2, Loader2, Move, Paintbrush, RotateCcw, Undo2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

interface Props {
  photoUrl: string;
  name: string;
  onDone: (file: File) => void;
  onCancel: () => void;
  cancelLabel?: string;
  text?: TextState | null; // 결과 화면: 미리보기에만 글자를 얹어 보여 줌. 저장되는 사진에는 안 들어감
}

type Tool = "erase" | "restore" | "move";
const UNDO_MAX = 20; // ponytail: 마스크가 장당 약 1MB(1024²)라 20번까지. 큰 사진이 많아지면 줄일 것
const SAMPLE = 2; // 누른 곳 주변 5x5 평균 색으로 비교 (포토샵 Magic Wand의 "5x5 평균")

/** 올린 사진의 배경을 브라우저에서 지우고, 상품만 남긴 뒤 옮기거나 돌려서 단색 배경 위에 놓음 */
export function CutoutEditor({ photoUrl, name, onDone, onCancel, cancelLabel = "원래 사진 그대로 쓰기", text }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [pixels, setPixels] = useState<Uint8ClampedArray | null>(null);
  const [first, setFirst] = useState<Uint8ClampedArray | null>(null); // AI가 처음 만든 마스크
  const [history, setHistory] = useState<Uint8ClampedArray[]>([]); // 마지막이 지금 마스크
  const [tool, setTool] = useState<Tool>("erase");
  const [tolerance, setTolerance] = useState(48);
  const [fill, setFill] = useState<string>(FILLS[0].color);
  const [place, setPlace] = useState<Place>(HOME);
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState("");
  const grab = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const mask = history.at(-1);
  const cut = useMemo(() => (img && mask ? cutOf(img, mask) : null), [img, mask]);

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
    const canvas = canvasRef.current;
    if (!cut || !canvas) return;
    compose(canvas, cut, fill, place);
    if (!text) return;
    // 합친 그림 위에 글자. 글꼴을 못 받아도 기본 글꼴로 그림
    let alive = true;
    const bg = document.createElement("canvas");
    compose(bg, cut, fill, place);
    loadFont(TEXT_STYLES.find((s) => s.id === text.style) ?? TEXT_STYLES[0])
      .catch(() => {})
      .then(() => alive && drawText(canvas, bg, text));
    return () => {
      alive = false;
    };
  }, [cut, fill, place, text]);

  /** 화면 좌표 → 그림 픽셀 좌표 */
  function point(e: React.PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * e.currentTarget.width, y: ((e.clientY - r.top) / r.height) * e.currentTarget.height };
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!img || !pixels || !mask) return;
    const p = point(e);
    if (tool === "move") {
      e.currentTarget.setPointerCapture(e.pointerId);
      grab.current = { x: p.x, y: p.y, px: place.x, py: place.y };
      return;
    }
    // 상품을 옮기거나 돌렸어도 원본 사진의 어느 픽셀을 눌렀는지 거꾸로 찾음
    const w = img.naturalWidth, h = img.naturalHeight;
    const src = placeMatrix(w, h, place).inverse().transformPoint(new DOMPoint(p.x, p.y));
    const x = Math.floor(src.x), y = Math.floor(src.y);
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const next = floodFill(pixels, mask, w, h, x, y, tool === "erase" ? 0 : 255, tolerance, SAMPLE);
    setHistory([...history.slice(-(UNDO_MAX - 1)), next]);
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!grab.current || !img) return;
    const p = point(e);
    const g = grab.current;
    setPlace({ ...place, x: g.px + (p.x - g.x) / img.naturalWidth, y: g.py + (p.y - g.y) / img.naturalHeight });
  }

  function done() {
    if (!cut) return;
    // 글자 없는 사진만 넘김 (글자는 결과 화면이 따로 얹음)
    const out = document.createElement("canvas");
    compose(out, cut, fill, place);
    out.toBlob((blob) => {
      if (!blob) return setError("사진을 만들지 못했어요. 다시 해 주세요.");
      onDone(new File([blob], name.replace(/\.\w+$/, "") + "-배경.png", { type: "image/png" }));
    }, "image/png");
  }

  if (error)
    return (
      <Notice action={<button type="button" className="btn-line min-h-[44px] px-4" onClick={onCancel}>{cancelLabel}</button>}>
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

  const changed = mask !== first;
  const moved = JSON.stringify(place) !== JSON.stringify(HOME);
  const slider = (label: string, key: "scale" | "rotate" | "skew", min: number, max: number, step: number, unit: (v: number) => string) => (
    <div>
      <label htmlFor={`place-${key}`} className="label">
        {label} <span className="hint">{unit(place[key])}</span>
      </label>
      <input id={`place-${key}`} type="range" min={min} max={max} step={step} value={place[key]} onChange={(e) => setPlace({ ...place, [key]: Number(e.target.value) })} className="w-full accent-ink" />
    </div>
  );

  return (
    <section className="card flex flex-col gap-6" aria-label="배경 지우기">
      <div className="overflow-hidden rounded-card shadow-sm">
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={tool === "move" ? "배경을 지운 미리보기. 끌어서 상품을 옮겨요" : "배경을 지운 미리보기. 누르면 비슷한 색 영역을 지우거나 살려요"}
          className={`block h-auto w-full touch-none ${tool === "move" ? "cursor-move" : "cursor-crosshair"}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={() => (grab.current = null)}
          onPointerCancel={() => (grab.current = null)}
        />
      </div>
      {text && <p className="-mt-4 hint">글자는 미리 보기용이에요. 위치·스타일은 다음 단계 &quot;글자 직접 고치기&quot;에서 바꿔요.</p>}

      <fieldset className="flex flex-col gap-4">
        <legend className="label">1. 지우기 다듬기</legend>
        <p className="-mt-3 hint">AI가 지우고 남은 배경이나, 잘못 지운 상품 부분을 사진에서 눌러 고쳐요. 비슷한 색이 이어진 곳이 한 번에 바뀌어요.</p>
        <div className="flex flex-wrap gap-2">
          <Chip on={tool === "erase"} onClick={() => setTool("erase")}>
            <Eraser aria-hidden className="size-4" /> 남은 배경 지우기
          </Chip>
          <Chip on={tool === "restore"} onClick={() => setTool("restore")}>
            <Paintbrush aria-hidden className="size-4" /> 지워진 상품 되살리기
          </Chip>
        </div>
        <div>
          <label htmlFor="tolerance" className="label">
            한 번에 바뀌는 범위 <span className="hint">{tolerance <= 30 ? "좁게" : tolerance <= 70 ? "보통" : "넓게"}</span>
          </label>
          <input id="tolerance" type="range" min={10} max={120} step={2} value={tolerance} onChange={(e) => setTolerance(Number(e.target.value))} className="w-full accent-ink" />
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="chip" disabled={history.length < 2} onClick={() => setHistory(history.slice(0, -1))}>
            <Undo2 aria-hidden className="size-4" /> 방금 누른 것 취소 {history.length > 1 && `(${history.length - 1})`}
          </button>
          <button type="button" className="chip" disabled={!changed} onClick={() => first && setHistory([first])}>
            <RotateCcw aria-hidden className="size-4" /> AI가 처음 지운 상태로
          </button>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="label">2. 상품 위치·모양</legend>
        <div className="flex flex-wrap gap-2">
          <Chip on={tool === "move"} onClick={() => setTool("move")}>
            <Move aria-hidden className="size-4" /> 끌어서 옮기기
          </Chip>
          <button type="button" className="chip" aria-pressed={place.flipX} onClick={() => setPlace({ ...place, flipX: !place.flipX })}>
            <FlipHorizontal2 aria-hidden className="size-4" /> 좌우 뒤집기
          </button>
          <button type="button" className="chip" aria-pressed={place.flipY} onClick={() => setPlace({ ...place, flipY: !place.flipY })}>
            <FlipVertical2 aria-hidden className="size-4" /> 상하 뒤집기
          </button>
          <button type="button" className="chip" disabled={!moved} onClick={() => setPlace(HOME)}>
            <RotateCcw aria-hidden className="size-4" /> 처음 위치로
          </button>
        </div>
        {slider("크기", "scale", 0.3, 2, 0.05, (v) => `${Math.round(v * 100)}%`)}
        {slider("돌리기", "rotate", -180, 180, 1, (v) => `${v}°`)}
        {slider("기울이기", "skew", -45, 45, 1, (v) => `${v}°`)}
      </fieldset>

      <fieldset>
        <legend className="label">3. 배경 색</legend>
        <div className="flex flex-wrap items-center gap-2">
          {FILLS.map((f) => (
            <button
              key={f.color}
              type="button"
              aria-pressed={fill === f.color}
              aria-label={f.name}
              title={f.name}
              onClick={() => setFill(f.color)}
              className={`size-11 rounded-full border-2 ${fill === f.color ? "border-ink ring-2 ring-ink ring-offset-2" : "border-mist"}`}
              style={{ background: f.color }}
            />
          ))}
          <label className="chip cursor-pointer">
            <input type="color" value={fill} onChange={(e) => setFill(e.target.value)} className="size-6 cursor-pointer rounded-full border-0 bg-transparent p-0" />
            다른 색 고르기
          </label>
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <button type="button" className="btn-fill" onClick={done}>
          <Check aria-hidden className="size-5" /> 이 사진으로 쓰기
        </button>
        <button type="button" className="btn-line" onClick={onCancel}>
          {cancelLabel}
        </button>
      </div>
    </section>
  );
}
