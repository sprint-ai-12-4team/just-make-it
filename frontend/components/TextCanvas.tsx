"use client";

import { loadImage } from "@/lib/draw";
import { drawText, loadFont, TEXT_STYLES, type TextState } from "@/lib/textStyles";
import { useEffect, useRef, useState, type RefObject } from "react";

interface Props {
  src: string; // 글자 없는 원본 (background_url)
  state: TextState;
  onChange: (s: TextState) => void;
  canvasRef: RefObject<HTMLCanvasElement | null>;
}

const clamp = (v: number) => Math.min(1, Math.max(0, v));
const STEP = 0.02; // 방향키 한 번에 움직이는 거리

/** 원본 위 문구를 끌어서(또는 방향키로) 옮기는 canvas. 저장도 이 canvas를 그대로 씀 */
export function TextCanvas({ src, state, onChange, canvasRef }: Props) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [failed, setFailed] = useState(false);
  const grab = useRef<{ dx: number; dy: number } | null>(null);

  useEffect(() => {
    loadImage(src).then(setImg, () => setFailed(true));
  }, [src]);

  useEffect(() => {
    if (!img || !canvasRef.current) return;
    const style = TEXT_STYLES.find((s) => s.id === state.style) ?? TEXT_STYLES[0];
    let alive = true;
    // 글꼴을 못 받아도 기본 글꼴로 그림
    loadFont(style)
      .catch(() => {})
      .then(() => alive && canvasRef.current && drawText(canvasRef.current, img, state));
    return () => {
      alive = false;
    };
  }, [img, state, canvasRef]);

  function point(e: React.PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const move = { ArrowLeft: [-STEP, 0], ArrowRight: [STEP, 0], ArrowUp: [0, -STEP], ArrowDown: [0, STEP] }[e.key];
    if (!move) return;
    e.preventDefault();
    onChange({ ...state, x: clamp(state.x + move[0]), y: clamp(state.y + move[1]) });
  }

  if (failed) return <p className="hint">원본 이미지를 불러오지 못했어요. 새로고침해 주세요.</p>;
  return (
    <canvas
      ref={canvasRef}
      role="img"
      tabIndex={0}
      aria-label={`광고 미리보기: ${state.text}. 방향키로 글자를 옮길 수 있어요`}
      className="preview cursor-move touch-none rounded-card bg-mist shadow-sm"
      onKeyDown={onKeyDown}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        const p = point(e);
        grab.current = { dx: state.x - p.x, dy: state.y - p.y }; // 잡은 곳 기준으로 움직여 글자가 튀지 않게
      }}
      onPointerMove={(e) => {
        if (!grab.current) return;
        const p = point(e);
        onChange({ ...state, x: clamp(p.x + grab.current.dx), y: clamp(p.y + grab.current.dy) });
      }}
      onPointerUp={() => (grab.current = null)}
      onPointerCancel={() => (grab.current = null)}
    />
  );
}
