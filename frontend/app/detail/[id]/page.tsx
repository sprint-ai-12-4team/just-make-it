"use client";

import { AdPreview } from "@/components/AdPreview";
import { Shell } from "@/components/Shell";
import { Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { loadImage, render, save, type Layout } from "@/lib/draw";
import type { DetailPage, Section } from "@/lib/types";
import { Download, Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const WIDTH = 860; // 스마트스토어 상세페이지 권장 가로폭
const LAYOUT: Layout = { pos: "bottom", big: false };
const SLOW_MS = 2 * 60 * 1000;
const ROLE_NAME = { hero: "대표", feature: "좋은 점", closing: "마무리" };

export default function Page() {
  return (
    <Shell>
      <DetailResultPage />
    </Shell>
  );
}

function DetailResultPage() {
  const { id } = useParams<{ id: string }>();
  const [page, setPage] = useState<DetailPage | null>(null);
  const [tick, setTick] = useState(0);
  const [error, setError] = useState("");
  const started = useRef(Date.now());

  useEffect(() => {
    api.getDetailPage(id).then(setPage).catch((e) => setError(e.message));
  }, [id, tick]);

  const live = !error && (!page || page.status === "processing" || page.sections.some((s) => s.status === "processing"));
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setTick((x) => x + 1), 2000);
    return () => clearInterval(t);
  }, [live]);

  async function redo(s: Section) {
    setError("");
    try {
      await api.regenerateSection(id, s.index, []);
      started.current = Date.now();
      setTick((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveAll() {
    const done = page!.sections.filter((s) => s.status === "success" && s.image_url);
    try {
      const imgs = await Promise.all(done.map((s) => loadImage(s.image_url!)));
      const canvas = document.createElement("canvas");
      await render(canvas, done.map((s, i) => ({ img: imgs[i], title: s.title ?? "", sub: s.body ?? "" })), LAYOUT, WIDTH);
      save(canvas, "상세페이지.png", setError);
    } catch {
      setError("저장하지 못했어요. 잠시 후 다시 시도해 주세요.");
    }
  }

  if (!page)
    return error ? (
      <Notice action={<Link href="/" className="btn-fill">처음으로</Link>}>{error}</Notice>
    ) : (
      <div aria-busy className="h-96 animate-pulse rounded-card bg-mist" />
    );

  const { done, total } = page.progress;
  const working = page.status === "processing";

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-h font-bold">{working ? "상세페이지를 만들고 있어요" : "상세페이지를 다 만들었어요!"}</h1>
        <p className="mt-2" aria-live="polite">
          {total}칸 중 {done}칸 완성{working && " · 다 된 칸부터 보여 드려요"}
        </p>
        <div className="mt-3 h-3 overflow-hidden rounded-full bg-mist" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total} aria-label="만든 칸 수">
          <div className="h-full rounded-full bg-ink transition-[width]" style={{ width: `${(done / total) * 100}%` }} />
        </div>
      </div>

      {live && Date.now() - started.current > SLOW_MS && (
        <Notice action={<button type="button" className="btn-fill" onClick={() => location.reload()}>새로고침</button>}>
          조금 더 걸리고 있어요. 잠시 뒤 새로고침해 보세요.
        </Notice>
      )}
      {page.status === "error" && <Notice action={<Link href="/" className="btn-fill">처음으로</Link>}>만들지 못했어요. 처음부터 다시 시도해 주세요.</Notice>}
      {error && <Notice>{error}</Notice>}

      {!working && done > 0 && (
        <button type="button" className="btn-fill" onClick={saveAll}>
          <Download aria-hidden className="size-5" /> 긴 이미지 한 장으로 저장
        </button>
      )}

      <ol className="flex flex-col gap-6">
        {page.sections.map((s) => (
          <li key={s.index} className="flex flex-col gap-3">
            <p className="font-semibold">
              {s.index + 1}. {ROLE_NAME[s.role]}
            </p>
            {s.status === "success" && s.image_url ? (
              <AdPreview width={WIDTH} layout={LAYOUT} panels={[{ src: s.image_url, title: s.title ?? "", sub: s.body ?? "" }]} />
            ) : (
              <div className="flex aspect-square flex-col items-center justify-center gap-3 rounded-card bg-mist p-6 text-center">
                {s.status === "error" ? (
                  <p className="font-medium">이 칸은 만들지 못했어요.</p>
                ) : (
                  <>
                    <Loader2 aria-hidden className="size-8 animate-spin" />
                    <p>{s.status === "pending" ? "순서를 기다리고 있어요" : "그림을 그리고 있어요"}</p>
                    {s.title && <p className="font-semibold">{s.title}</p>}
                  </>
                )}
              </div>
            )}
            {(s.status === "success" || s.status === "error") && (
              <button type="button" className="btn-line" disabled={working} onClick={() => redo(s)}>
                <RefreshCw aria-hidden className="size-5" /> 이 칸 그림만 다시 만들기
              </button>
            )}
          </li>
        ))}
      </ol>

      <Link href="/" className="btn-line">처음부터 새로 만들기</Link>
    </div>
  );
}
