"use client";

import { Shell } from "@/components/Shell";
import { TextCanvas } from "@/components/TextCanvas";
import { Chip, Notice, Waiting } from "@/components/ui";
import { api } from "@/lib/api";
import { save } from "@/lib/draw";
import { POSITION_Y, styleFor, TEXT_STYLES, type TextState } from "@/lib/textStyles";
import { ADJUSTMENTS, type Generation } from "@/lib/types";
import { Check, Download, Link2, Pencil, RefreshCw, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

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
  // null이면 서버가 얹은 image_url 그대로. 값이 있으면 background_url 위에 직접 얹는 중
  const [edit, setEdit] = useState<TextState | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getGeneration(id)
      .then(setG)
      .catch((e) => setError(e.message));
  }, [id]);

  /** 서버가 얹은 위치·크기·분위기에서 시작 */
  function startEdit(r: Generation) {
    const l = r.text_layout;
    setEdit({
      text: r.message,
      style: styleFor(r.input?.style).id,
      x: 0.5,
      y: POSITION_Y[l?.position ?? "top"],
      scale: l?.size_scale ?? 1,
    });
  }

  async function remake(adjustments: string[]) {
    if (!g?.input) return;
    setBusy(true);
    setError("");
    try {
      // ponytail: 원본 사진은 조회 응답에 없어 다시 만들 때 빠짐. 서버가 parent_id로 원본 사진을 재사용하면 해결
      // 직접 고친 문구를 이어 씀. g.input.message는 처음 입력값
      const message = edit?.text.trim() || g.message;
      const next = await api.generate({ ...g.input, message, style: g.input.style ?? null, adjustments, parent_id: g.id });
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

      {edit && g.background_url ? (
        <TextCanvas src={g.background_url} state={edit} onChange={setEdit} canvasRef={canvasRef} />
      ) : (
        <div className="overflow-hidden rounded-card bg-mist shadow-sm">
          {/* eslint-disable-next-line @next/next/no-img-element -- 서버가 만든 최종 이미지 그대로 (프록시 경유) */}
          <img src={g.image_url} alt={g.message} width={g.width} height={g.height} className="block h-auto w-full" />
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {edit ? (
          <button type="button" className="btn-fill" onClick={() => save(canvasRef.current, `광고-${edit.text.slice(0, 10)}.png`, setError)}>
            <Download aria-hidden className="size-5" /> 내 기기에 저장
          </button>
        ) : (
          // 프록시 덕분에 같은 출처라 download 속성이 동작
          <a className="btn-fill" href={g.image_url} download={`광고-${g.message.slice(0, 10)}.png`}>
            <Download aria-hidden className="size-5" /> 내 기기에 저장
          </a>
        )}
        <button type="button" className="btn-line" onClick={copyLink} aria-live="polite">
          {copied ? <Check aria-hidden className="size-5" /> : <Link2 aria-hidden className="size-5" />}
          {copied ? "링크를 복사했어요" : "링크 복사"}
        </button>
      </div>

      {error && <Notice>{error}</Notice>}

      {/* 원본이 없는 예전 결과는 직접 고치기 불가 */}
      {g.background_url &&
        (edit ? (
          <TextEditor state={edit} onChange={setEdit} onReset={() => setEdit(null)} />
        ) : (
          <button type="button" className="btn-line" onClick={() => startEdit(g)}>
            <Pencil aria-hidden className="size-5" /> 글자 직접 고치기
          </button>
        ))}

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
  state: TextState;
  onChange: (s: TextState) => void;
  onReset: () => void;
}

/** 문구·스타일·크기. 위치는 미리보기에서 끌어서 (또는 방향키) */
function TextEditor({ state, onChange, onReset }: EditorProps) {
  return (
    <section className="card flex flex-col gap-6">
      <h2 className="text-h-sm font-bold">글자 직접 고치기</h2>
      <p className="-mt-4 hint">그림은 그대로 두고 글자만 바꿔요. 위 이미지에서 글자를 끌어서 옮길 수 있어요.</p>
      <div>
        <label htmlFor="t" className="label">문구</label>
        <textarea id="t" rows={2} className="field" value={state.text} onChange={(e) => onChange({ ...state, text: e.target.value })} />
      </div>
      <fieldset>
        <legend className="label">글자 스타일</legend>
        <div className="flex flex-wrap gap-2">
          {TEXT_STYLES.map((s) => (
            <Chip key={s.id} on={state.style === s.id} onClick={() => onChange({ ...state, style: s.id })}>
              <span style={{ fontFamily: `"${s.font}"` }}>{s.name}</span>
            </Chip>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor="size" className="label">글자 크기</label>
        <input
          id="size"
          type="range"
          min={0.6}
          max={1.6}
          step={0.05}
          value={state.scale}
          onChange={(e) => onChange({ ...state, scale: Number(e.target.value) })}
          className="w-full accent-ink"
        />
      </div>
      <button type="button" className="btn-line" onClick={onReset}>
        <Undo2 aria-hidden className="size-5" /> 처음 이미지로 돌아가기
      </button>
    </section>
  );
}
