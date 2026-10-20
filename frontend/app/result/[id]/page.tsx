"use client";

import { AdPreview } from "@/components/AdPreview";
import { Shell } from "@/components/Shell";
import { Chip, Notice, Waiting } from "@/components/ui";
import { api } from "@/lib/api";
import { save, type Layout, type Pos } from "@/lib/draw";
import { ADJUSTMENTS, type Generation } from "@/lib/types";
import { Check, Download, Link2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const POSITIONS: [Pos, string][] = [["top", "위"], ["middle", "가운데"], ["bottom", "아래"]];

export default function Page() {
  return (
    <Shell>
      <ResultPage />
    </Shell>
  );
}

function ResultPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [g, setG] = useState<Generation | null>(null);
  const [title, setTitle] = useState("");
  const [sub, setSub] = useState("");
  const [layout, setLayout] = useState<Layout>({ pos: "bottom", big: false });
  const [picked, setPicked] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getGeneration(id)
      .then((r) => {
        setG(r);
        setTitle(r.message);
        setSub(r.input?.product_name ?? "");
      })
      .catch((e) => setError(e.message));
  }, [id]);

  async function remake(adjustments: string[]) {
    if (!g?.input) return;
    setBusy(true);
    setError("");
    try {
      // ponytail: 원본 사진은 조회 응답에 없어 다시 만들 때 빠짐. 서버가 parent_id로 원본 사진을 재사용하면 해결
      const next = await api.generate({ ...g.input, style: g.input.style ?? null, adjustments, parent_id: g.id });
      router.push(`/result/${next.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function copyLink() {
    await navigator.clipboard.writeText(location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (busy) return <Waiting title="새로 만들고 있어요" hint="보통 10~30초 걸려요. 이 화면을 닫지 말아 주세요." />;
  if (!g)
    return error ? (
      <Notice action={<Link href="/" className="btn-fill">처음으로</Link>}>{error}</Notice>
    ) : (
      <div aria-busy className="aspect-square animate-pulse rounded-card bg-mist" />
    );

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-h font-bold">다 만들었어요!</h1>

      <AdPreview canvasRef={canvasRef} width={g.width} layout={layout} panels={[{ src: g.image_url, title, sub }]} />

      <div className="grid gap-3 sm:grid-cols-2">
        <button type="button" className="btn-fill" onClick={() => save(canvasRef.current, `광고-${title.slice(0, 10)}.png`, setError)}>
          <Download aria-hidden className="size-5" /> 내 기기에 저장
        </button>
        <button type="button" className="btn-line" onClick={copyLink} aria-live="polite">
          {copied ? <Check aria-hidden className="size-5" /> : <Link2 aria-hidden className="size-5" />}
          {copied ? "링크를 복사했어요" : "링크 복사"}
        </button>
      </div>

      {error && <Notice>{error}</Notice>}

      <section className="card flex flex-col gap-6">
        <h2 className="text-h-sm font-bold">글자 고치기</h2>
        <p className="-mt-4 hint">바로 위 이미지에 반영돼요. 다시 만들 필요 없어요.</p>
        <div>
          <label htmlFor="t" className="label">큰 글자</label>
          <textarea id="t" rows={2} className="field" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label htmlFor="s" className="label">작은 글자</label>
          <input id="s" className="field" value={sub} onChange={(e) => setSub(e.target.value)} />
        </div>
        <fieldset>
          <legend className="label">글자 위치</legend>
          <div className="flex flex-wrap gap-2">
            {POSITIONS.map(([v, t]) => (
              <Chip key={v} on={layout.pos === v} onClick={() => setLayout({ ...layout, pos: v })}>{t}</Chip>
            ))}
            <Chip on={layout.big} onClick={() => setLayout({ ...layout, big: !layout.big })}>글자 더 크게</Chip>
          </div>
        </fieldset>
      </section>

      <section className="card flex flex-col gap-6">
        <h2 className="text-h-sm font-bold">그림이 마음에 안 드세요?</h2>
        <fieldset>
          <legend className="label">이렇게 바꿔 주세요 (여러 개 골라도 돼요)</legend>
          <div className="flex flex-wrap gap-2">
            {ADJUSTMENTS.map((a) => (
              <Chip key={a} on={picked.includes(a)} onClick={() => setPicked(picked.includes(a) ? picked.filter((x) => x !== a) : [...picked, a])}>{a}</Chip>
            ))}
          </div>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" className="btn-fill" disabled={!picked.length} onClick={() => remake(picked)}>
            고른 대로 다시 만들기
          </button>
          <button type="button" className="btn-line" onClick={() => remake([])}>
            <RefreshCw aria-hidden className="size-5" /> 그냥 한 번 더 만들기
          </button>
        </div>
      </section>

      <Link href="/" className="btn-line">처음부터 새로 만들기</Link>
    </div>
  );
}
