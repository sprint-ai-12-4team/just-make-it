"use client";

import { Notice } from "@/components/ui";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import type { DailyStats, EvalSummary, Stats } from "@/lib/types";
import { useEffect, useState } from "react";

// 발표·운영용 숨김 페이지 (nav 링크 없음). 서빙에 없는 칸은 "-"
const pct = (v?: number | null) => (v == null ? "-" : `${Math.round(v * 1000) / 10}%`);
const sec = (v?: number | null) => (v == null ? "-" : `${v.toFixed(1)}초`);
const usd = (v?: number | null) => (v == null ? "-" : `$${v < 0.1 ? v.toFixed(4) : v.toFixed(2)}`);
const num = (v?: number | null) => (v == null ? "-" : String(Math.round(v * 1000) / 1000));

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card bg-honey p-4">
      <p className="text-sub">{label}</p>
      <p className="text-h-sm font-bold">{value}</p>
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sub">
        <thead>
          <tr>{head.map((h) => <th key={h} className="px-2 py-1 text-left font-bold">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-ink/10">{r.map((c, j) => <td key={j} className="px-2 py-1">{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function StatsPage() {
  const [days, setDays] = useState(7);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [ev, setEv] = useState<EvalSummary | null | undefined>(undefined); // undefined=불러오는 중, null=없음

  useEffect(() => {
    setError("");
    api.getStats(days).then(setStats, (e) => setError(e.message));
  }, [days]);

  useEffect(() => {
    fetch("/eval/summary.json").then((r) => (r.ok ? r.json() : null)).catch(() => null).then(setEv);
  }, []);

  const t = stats?.total;
  const ref = t?.by_reference;
  return (
    <Shell>
      <h1 className="text-h-sm font-bold">정량평가</h1>
      <label className="mt-4 block">
        기간{" "}
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-btn border border-ink/20 px-2 py-1">
          {[7, 30, 90].map((d) => <option key={d} value={d}>최근 {d}일</option>)}
        </select>
      </label>
      {error && <div className="mt-4"><Notice>{error}</Notice></div>}
      {stats && t && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Tile label="생성 수" value={String(t.generated)} />
            <Tile label="다운로드율" value={pct(t.download_rate)} />
            <Tile label="직접 고침율" value={pct(t.edit_rate)} />
            <Tile label="다시 만들기율" value={pct(t.remake_rate)} />
            <Tile label="생성 시간 p50 / p95" value={`${sec(t.seconds_p50)} / ${sec(t.seconds_p95)}`} />
            <Tile label="로컬 GPU 비율" value={pct(t.local_rate)} />
            <Tile label="1장당 비용" value={usd(t.cost_per_image_usd)} />
            <Tile label="실패율" value={pct(t.error_rate)} />
          </div>
          {ref && (
            <section className="mt-8">
              <h2 className="mb-2 font-bold">참고 사진별 비교</h2>
              <Table
                head={["구분", "생성 수", "다운로드율", "다시 만들기율"]}
                rows={([["사진 직접 올림", ref.upload], ["Pixabay 고름", ref.stock], ["사진 없음", ref.none]] as const).map(([n, r]) => [n, String(r?.generated ?? "-"), pct(r?.download_rate), pct(r?.remake_rate)])}
              />
            </section>
          )}
          <section className="mt-8">
            <h2 className="mb-2 font-bold">날짜별</h2>
            <Table
              head={["날짜", "생성", "다운로드", "직접 고침", "다시 만들기"]}
              rows={stats.days.map((d: DailyStats) => [d.date, String(d.generated), pct(d.download_rate), pct(d.edit_rate), pct(d.remake_rate)])}
            />
          </section>
        </>
      )}
      <section className="mt-8">
        <h2 className="mb-2 font-bold">모델 오프라인 평가</h2>
        {ev === null && <p>모델 오프라인 평가 결과가 아직 없어요</p>}
        {ev && (
          <>
            <p className="mb-2 text-sub">{ev.generated_at}</p>
            <Table
              head={["실행", "케이스", "평균 시간", "p95 시간", "비용", "Fallback", "CLIP", "참고 유사도", "OCR 일치"]}
              rows={ev.runs.map((r) => [r.run_id, String(r.cases), sec(r.avg_seconds), sec(r.p95_seconds), usd(r.cost_usd), pct(r.fallback_rate), num(r.clip_score), num(r.ref_similarity), pct(r.ocr_match)])}
            />
          </>
        )}
      </section>
    </Shell>
  );
}
