"use client";

import { loadImage } from "@/lib/draw";
import { drawText, loadFonts, type Box, type TextState, type WordState } from "@/lib/textStyles";
import { useEffect, useRef, useState, type RefObject } from "react";

interface Props {
  src: string; // 글자 없는 원본 (background_url)
  state: TextState;
  onChange: (s: TextState) => void;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  selected?: number | null; // 단어별 편집 중 고른 단어
  onSelect?: (i: number | null) => void;
}

const clamp = (v: number) => Math.min(1, Math.max(0, v));
const STEP = 0.02; // 방향키 한 번에 움직이는 거리
const inside = (b: Box, p: { x: number; y: number }) => p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h;

type Grab = { dx: number; dy: number } | { word: number; dx: number; dy: number } | { x: number; y: number; words: WordState[] };

/** 원본 위 문구를 끌어서(또는 방향키로) 옮기는 canvas. 단어별 편집이면 누른 단어만, 빈 곳을 끌면 전체를 옮김.
 *  저장도 이 canvas를 그대로 씀 (고른 단어 테두리는 canvas 밖에 그려서 저장에 안 들어감) */
export function TextCanvas({ src, state, onChange, canvasRef, selected = null, onSelect }: Props) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const grab = useRef<Grab | null>(null);

  useEffect(() => {
    loadImage(src).then(setImg, () => setFailed(true));
  }, [src]);

  useEffect(() => {
    if (!img || !canvasRef.current) return;
    let alive = true;
    loadFonts(state).then(() => alive && canvasRef.current && setBoxes(drawText(canvasRef.current, img, state)));
    return () => {
      alive = false;
    };
  }, [img, state, canvasRef]);

  function point(e: React.PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
  }

  const moveWords = (words: WordState[], dx: number, dy: number, only: number | null = null) =>
    words.map((w, i) => (only === null || i === only ? { ...w, x: clamp(w.x + dx), y: clamp(w.y + dy) } : w));

  function onKeyDown(e: React.KeyboardEvent) {
    const move = { ArrowLeft: [-STEP, 0], ArrowRight: [STEP, 0], ArrowUp: [0, -STEP], ArrowDown: [0, STEP] }[e.key];
    if (!move) return;
    e.preventDefault();
    if (state.words) onChange({ ...state, words: moveWords(state.words, move[0], move[1], selected) });
    else onChange({ ...state, x: clamp(state.x + move[0]), y: clamp(state.y + move[1]) });
  }

  if (failed) return <p className="hint">원본 이미지를 불러오지 못했어요. 새로고침해 주세요.</p>;
  const label = state.words
    ? `광고 미리보기: ${state.text}. 단어를 눌러 고르고 끌어서 옮겨요. 방향키는 ${selected === null ? "전체" : "고른 단어"}를 옮겨요`
    : `광고 미리보기: ${state.text}. 방향키로 글자를 옮길 수 있어요`;
  return (
    <>
      <canvas
        ref={canvasRef}
        role="img"
        tabIndex={0}
        aria-label={label}
        className="preview cursor-move touch-none rounded-card bg-mist shadow-sm"
        onKeyDown={onKeyDown}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          const p = point(e);
          if (!state.words) {
            grab.current = { dx: state.x - p.x, dy: state.y - p.y }; // 잡은 곳 기준으로 움직여 글자가 튀지 않게
            return;
          }
          // 겹치면 나중에 그린(위에 보이는) 단어를 고름
          const hit = boxes.findLastIndex((b) => inside(b, p));
          onSelect?.(hit < 0 ? null : hit);
          grab.current = hit < 0 ? { x: p.x, y: p.y, words: state.words } : { word: hit, dx: state.words[hit].x - p.x, dy: state.words[hit].y - p.y };
        }}
        onPointerMove={(e) => {
          const g = grab.current;
          if (!g) return;
          const p = point(e);
          if ("words" in g) onChange({ ...state, words: moveWords(g.words, p.x - g.x, p.y - g.y) });
          else if ("word" in g && state.words)
            onChange({ ...state, words: state.words.map((w, i) => (i === g.word ? { ...w, x: clamp(p.x + g.dx), y: clamp(p.y + g.dy) } : w)) });
          else onChange({ ...state, x: clamp(p.x + g.dx), y: clamp(p.y + g.dy) });
        }}
        onPointerUp={() => (grab.current = null)}
        onPointerCancel={() => (grab.current = null)}
      />
      {/* 화면에만 보이는 단어 테두리. 부모가 relative + 그림 크기(w-fit) */}
      {state.words &&
        boxes.map((b, i) => (
          <div
            key={i}
            aria-hidden
            className={`pointer-events-none absolute rounded-sm border-2 ${i === selected ? "border-ink" : "border-dashed border-white/70"}`}
            style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}
          />
        ))}
    </>
  );
}
