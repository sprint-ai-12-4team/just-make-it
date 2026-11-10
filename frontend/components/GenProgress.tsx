"use client";

import { api } from "@/lib/api";
import { elapsedMs, nextPercent, statusText } from "@/lib/progress";
import { pickTips } from "@/lib/tips";
import type { Generation, Tip } from "@/lib/types";
import { ChevronLeft, ChevronRight, ExternalLink, Lightbulb, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const say = (s: number) => (s < 60 ? `약 ${Math.max(1, Math.round(s))}초` : `약 ${Math.round(s / 60)}분`);

/** 비동기 생성 대기: 막대 + 기다리는 동안 볼 정보 카드 (api_spec V3, service_consulting.md A·C) */
export function GenProgress({ g }: { g: Generation }) {
  const { progress } = g;
  const [opened] = useState(() => Date.now());
  const [now, setNow] = useState(opened);
  // 서버 값을 받은 시각 기준으로 남은 시간·지난 시간을 0.5초마다 줄여 보여 줌
  const [got, setGot] = useState<{ at: number; left: number; elapsed?: number } | null>(null);
  const pct = useRef(0);

  useEffect(() => {
    if (progress) setGot({ at: Date.now(), left: progress.estimated_seconds * 1000, elapsed: progress.elapsed_seconds });
  }, [progress]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);

  const elapsed = elapsedMs(now, opened, g.created_at, got?.elapsed != null ? { elapsed: got.elapsed, at: got.at } : undefined);
  const left = got === null ? null : Math.max(0, got.left - (now - got.at));
  const overdue = !!progress?.overdue || (left !== null && left === 0 && progress?.stage === "running");
  pct.current = nextPercent(pct.current, elapsed, left, progress);
  const shown = left === null ? null : Math.round(pct.current);
  const status = statusText(progress, overdue);
  const time = left === null || overdue ? "" : left > 0 ? `${say(left / 1000)} 남았어요` : "거의 다 됐어요";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-5 rounded-card bg-honey px-6 py-10">
        <p className="text-h-sm font-bold">이미지를 만들고 있어요</p>
        <p>
          넣을 문구 <span className="font-semibold">“{g.message}”</span>
        </p>
        <div
          role="progressbar"
          aria-label="만드는 중"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={shown ?? undefined}
          aria-valuetext={[status, time].filter(Boolean).join(", ")}
          className="h-3 overflow-hidden rounded-full bg-white"
        >
          <div className={shown === null ? "h-full w-1/3 animate-pulse bg-ink" : "h-full bg-ink transition-[width] duration-500"} style={shown === null ? undefined : { width: `${shown}%` }} />
        </div>
        <p aria-live="polite" className="flex flex-wrap justify-between gap-2 font-medium">
          <span>{status}</span>
          <span>{time}</span>
        </p>
        <p className="hint text-ink">이 화면을 닫아도 계속 만들어요. 같은 주소로 다시 열면 이어서 볼 수 있어요.</p>
      </div>
      <TipCards g={g} />
    </div>
  );
}

const EVERY = 8000;

/** 정보 카드. 서버 카드가 없으면(404 등) 기본 카드. 8초마다 넘김, 직접 넘기거나 멈출 수 있음 (WCAG 2.2.2) */
function TipCards({ g }: { g: Generation }) {
  const purpose = g.input?.purpose;
  const [tips, setTips] = useState<Tip[]>(() => pickTips(purpose, new Date()));
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .getTips(purpose)
      .then((t) => alive && t.length > 0 && (setTips(t), setI(0)))
      .catch(() => {});
    // 움직임 줄이기를 켠 사용자는 자동으로 넘기지 않음
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) setAuto(false);
    return () => {
      alive = false;
    };
  }, [purpose]);
  useEffect(() => {
    if (!auto || tips.length < 2) return;
    const t = setInterval(() => setI((x) => (x + 1) % tips.length), EVERY);
    return () => clearInterval(t);
  }, [auto, tips.length]);

  const tip = tips[i];
  if (!tip) return null;
  const go = (d: number) => (setAuto(false), setI((i + d + tips.length) % tips.length));
  const link = tip.action ?? (tip.source ? { label: `${tip.source.name}에서 보기`, href: tip.source.url } : null);

  return (
    <section aria-roledescription="carousel" aria-label="기다리는 동안 알아 두면 좋은 것" className="card flex flex-col gap-4">
      <p className="flex items-center gap-2 font-semibold">
        <Lightbulb aria-hidden className="size-5" /> 기다리는 동안 알아 두세요
      </p>
      {/* 자동으로 넘길 때는 읽어 주지 않음 (화면 읽기 프로그램 사용자가 방해받지 않게) */}
      <div aria-live={auto ? "off" : "polite"} aria-roledescription="slide" aria-label={`${tips.length}개 중 ${i + 1}번째`} className="min-h-[120px]">
        <h2 className="text-sub font-semibold">{tip.title}</h2>
        {tip.body && <p className="mt-2">{tip.body}</p>}
        {tip.kind === "law" && <p className="mt-2 hint">법률 자문이 아니에요. 정확한 내용은 공식 기관에 확인해 주세요.</p>}
        {link && (
          <a
            href={link.href}
            target={/^https?:/.test(link.href) ? "_blank" : undefined}
            rel="noopener noreferrer"
            onClick={() => api.logEvent(g.id, "tip_click", { tip_id: tip.id })}
            className="mt-3 inline-flex min-h-[44px] items-center gap-1.5 font-medium underline underline-offset-4"
          >
            {link.label} <ExternalLink aria-hidden className="size-4" />
          </a>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="hint">
          {i + 1} / {tips.length}
        </span>
        <div className="flex gap-2">
          <button type="button" className="chip" onClick={() => setAuto(!auto)} aria-label={auto ? "자동 넘기기 멈추기" : "자동 넘기기 다시 시작"}>
            {auto ? <Pause aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
          </button>
          <button type="button" className="chip" onClick={() => go(-1)} aria-label="이전 카드">
            <ChevronLeft aria-hidden className="size-4" />
          </button>
          <button type="button" className="chip" onClick={() => go(1)} aria-label="다음 카드">
            <ChevronRight aria-hidden className="size-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
