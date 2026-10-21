"use client";

import { loadImage, render, type Layout } from "@/lib/draw";
import { useEffect, useRef, useState, type RefObject } from "react";

interface Props {
  panels: { src: string; title: string; sub?: string }[];
  layout: Layout;
  width: number;
  canvasRef?: RefObject<HTMLCanvasElement | null>;
}

/** 이미지 + 문구 미리보기. 다운로드도 이 canvas를 그대로 저장 */
export function AdPreview({ panels, layout, width, canvasRef: given }: Props) {
  const own = useRef<HTMLCanvasElement>(null);
  const canvasRef = given ?? own;
  const [failed, setFailed] = useState(false);
  const key = JSON.stringify(panels);

  useEffect(() => {
    let alive = true;
    Promise.all(panels.map((p) => loadImage(p.src)))
      .then((imgs) => {
        if (alive && canvasRef.current)
          return render(canvasRef.current, imgs.map((img, i) => ({ ...panels[i], img })), layout, width);
      })
      .then(() => alive && setFailed(false))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, layout.pos, layout.big, width]);

  return (
    <div className="overflow-hidden rounded-card bg-mist shadow-sm">
      <canvas ref={canvasRef} role="img" aria-label={panels.map((p) => p.title).join(" / ")} className="block h-auto w-full" />
      {failed && <p className="p-6 hint">이미지를 불러오지 못했어요. 새로고침해 주세요.</p>}
    </div>
  );
}
