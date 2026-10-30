"use client";

import type { GenProgress as Progress } from "@/lib/types";
import { useEffect, useState } from "react";

const say = (s: number) => (s < 60 ? `약 ${Math.max(1, Math.round(s))}초` : `약 ${Math.round(s / 60)}분`);

/** 비동기 생성 대기: 서버가 알려 준 남은 시간으로 막대를 채움 (api_spec V3). 끝까지 차지 않게 95%에서 멈춤 */
export function GenProgress({ message, progress }: { message: string; progress?: Progress | null }) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  const [deadline, setDeadline] = useState<number | null>(null);

  // 조회할 때마다(2초) 남은 시간을 새로 맞추고, 그 사이는 0.5초마다 줄여 보여 줌
  useEffect(() => {
    if (progress) setDeadline(Date.now() + progress.estimated_seconds * 1000);
  }, [progress]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);

  const elapsed = now - start;
  const left = deadline === null ? null : Math.max(0, deadline - now);
  const pct = left === null ? null : Math.min(95, Math.round((100 * elapsed) / (elapsed + left || 1)));
  const status =
    progress?.stage === "queued" && progress.jobs_ahead > 0
      ? `앞에 ${progress.jobs_ahead}건 기다리는 중`
      : progress?.stage === "queued"
        ? "곧 시작해요"
        : "그림을 그리고 있어요";
  const time = left === null ? "" : left > 0 ? `${say(left / 1000)} 남았어요` : "거의 다 됐어요";

  return (
    <div className="flex flex-col gap-5 rounded-card bg-honey px-6 py-12">
      <p className="text-h-sm font-bold">이미지를 만들고 있어요</p>
      <p>
        넣을 문구 <span className="font-semibold">“{message}”</span>
      </p>
      <div
        role="progressbar"
        aria-label="만드는 중"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-valuetext={[status, time].filter(Boolean).join(", ")}
        className="h-3 overflow-hidden rounded-full bg-white"
      >
        <div className={pct === null ? "h-full w-1/3 animate-pulse bg-ink" : "h-full bg-ink transition-[width] duration-500"} style={pct === null ? undefined : { width: `${pct}%` }} />
      </div>
      <p aria-live="polite" className="flex flex-wrap justify-between gap-2 font-medium">
        <span>{status}</span>
        <span>{time}</span>
      </p>
      <p className="hint text-ink">이 화면을 닫아도 계속 만들어요. 같은 주소로 다시 열면 이어서 볼 수 있어요.</p>
    </div>
  );
}
