"use client";

import clsx from "clsx";
import { useRef, useState } from "react";

export interface Slide {
  label: string;
  node: React.ReactNode;
}

/** 아래 설정을 내려도 미리보기가 위에 붙어 있게. 그림이 여럿이면 가로로 넘겨 봄 */
export function StickyPreview({ slides }: { slides: Slide[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState(0);
  const go = (i: number) => ref.current?.scrollTo({ left: i * ref.current.clientWidth, behavior: "smooth" });

  return (
    <div className="sticky top-0 z-10 -mx-2 bg-white px-2 py-2">
      <div
        ref={ref}
        // 그림 위 드래그(글자 옮기기·지우기)는 canvas가 touch-none이라 안 넘어감 → 그림 밖 여백이나 아래 버튼으로 넘김
        onScroll={(e) => setAt(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
        className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {slides.map((s, i) => (
          <div key={s.label} className="w-full shrink-0 snap-start" aria-hidden={slides.length > 1 && i !== at} inert={slides.length > 1 && i !== at}>
            {s.node}
          </div>
        ))}
      </div>
      {slides.length > 1 && (
        <div className="mt-2 flex justify-center gap-2">
          {slides.map((s, i) => (
            <button key={s.label} type="button" aria-pressed={i === at} onClick={() => go(i)} className={clsx("chip", i === at && "chip-on")}>
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
