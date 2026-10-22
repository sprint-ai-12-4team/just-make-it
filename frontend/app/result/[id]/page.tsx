"use client";

import { Shell } from "@/components/Shell";
import { Chip, Notice, Waiting } from "@/components/ui";
import { api } from "@/lib/api";
import { ADJUSTMENTS, BIG_TEXT, FONTS, POSITIONS, type Generation, type TextLayout } from "@/lib/types";
import { Check, Download, Link2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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
  const [g, setG] = useState<Generation | null>(null);
  const [title, setTitle] = useState("");
  const [editing, setEditing] = useState(false);
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
      })
      .catch((e) => setError(e.message));
  }, [id]);

  /** 서버가 글자 없는 원본에 다시 얹음 (재생성 아님, 1초 이내) */
  async function editText(b: Partial<TextLayout> & { message?: string }) {
    setEditing(true);
    setError("");
    try {
      const next = await api.editText(id, b);
      setG(next);
      setTitle(next.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEditing(false);
    }
  }

  async function remake(adjustments: string[]) {
    if (!g?.input) return;
    setBusy(true);
    setError("");
    try {
      // ponytail: 원본 사진은 조회 응답에 없어 다시 만들 때 빠짐. 서버가 parent_id로 원본 사진을 재사용하면 해결
      // 글자 고치기로 바꾼 문구(g.message)를 이어 씀. g.input.message는 처음 입력값
      const next = await api.generate({ ...g.input, message: g.message, style: g.input.style ?? null, adjustments, parent_id: g.id });
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

      <div className="overflow-hidden rounded-card bg-mist shadow-sm" aria-busy={editing}>
        {/* eslint-disable-next-line @next/next/no-img-element -- 서버가 만든 최종 이미지 그대로 (프록시 경유) */}
        <img src={g.image_url} alt={g.message} width={g.width} height={g.height} className={`block h-auto w-full transition-opacity ${editing ? "opacity-60" : ""}`} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {/* 프록시 덕분에 같은 출처라 download 속성이 동작 */}
        <a className="btn-fill" href={g.image_url} download={`광고-${g.message.slice(0, 10)}.png`}>
          <Download aria-hidden className="size-5" /> 내 기기에 저장
        </a>
        <button type="button" className="btn-line" onClick={copyLink} aria-live="polite">
          {copied ? <Check aria-hidden className="size-5" /> : <Link2 aria-hidden className="size-5" />}
          {copied ? "링크를 복사했어요" : "링크 복사"}
        </button>
      </div>

      {error && <Notice>{error}</Notice>}

      {/* text_layout이 없으면 서빙이 아직 글자 고치기를 지원하지 않는 응답 (api_spec 10-22 결정 이전) */}
      {g.text_layout && (
        <TextEditor layout={g.text_layout} message={g.message} title={title} setTitle={setTitle} busy={editing} onEdit={editText} />
      )}

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

interface EditorProps {
  layout: TextLayout;
  message: string;
  title: string;
  setTitle: (v: string) => void;
  busy: boolean;
  onEdit: (b: Partial<TextLayout> & { message?: string }) => void;
}

/** 문구는 버튼으로, 위치·글꼴·크기는 누르는 즉시 서버에 반영 */
function TextEditor({ layout, message, title, setTitle, busy, onEdit }: EditorProps) {
  const big = layout.size_scale >= BIG_TEXT;
  return (
    <section className="card flex flex-col gap-6">
      <h2 className="text-h-sm font-bold">글자 고치기</h2>
      <p className="-mt-4 hint">그림은 그대로 두고 글자만 바꿔요.</p>
      <div>
        <label htmlFor="t" className="label">문구</label>
        <textarea id="t" rows={2} className="field" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button
          type="button"
          className="btn-line mt-3"
          disabled={busy || !title.trim() || title.trim() === message}
          onClick={() => onEdit({ message: title.trim() })}
        >
          문구 바꾸기
        </button>
      </div>
      <fieldset disabled={busy}>
        <legend className="label">글자 위치</legend>
        <div className="flex flex-wrap gap-2">
          {POSITIONS.map(([v, t]) => (
            <Chip key={v} on={layout.position === v} onClick={() => onEdit({ position: v })}>{t}</Chip>
          ))}
          <Chip on={big} onClick={() => onEdit({ size_scale: big ? 1 : BIG_TEXT })}>글자 더 크게</Chip>
        </div>
      </fieldset>
      <fieldset disabled={busy}>
        <legend className="label">글꼴</legend>
        <div className="flex flex-wrap gap-2">
          {FONTS.map(([v, t]) => (
            <Chip key={v} on={layout.font === v} onClick={() => onEdit({ font: v })}>{t}</Chip>
          ))}
        </div>
      </fieldset>
    </section>
  );
}
