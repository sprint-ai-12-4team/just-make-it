"use client";

import { CutoutEditor } from "@/components/CutoutEditor";
import { Shell } from "@/components/Shell";
import { TextCanvas } from "@/components/TextCanvas";
import { Chip, Notice, RiskyWords, Waiting } from "@/components/ui";
import { api } from "@/lib/api";
import { save } from "@/lib/draw";
import { loadCopies, POSITION_Y, saveCopies, styleFor, TEXT_STYLES, type TextState } from "@/lib/textStyles";
import { ADJUSTMENTS, type Generation, type Purpose } from "@/lib/types";
import { Check, Download, Eye, EyeOff, History, Link2, Pencil, RefreshCw, Scissors, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// 올린 뒤 화면에서 가려지거나 잘리는 곳 (그림 크기 대비 %)
// ponytail: 대략값. 인스타 프로필 격자는 3:4로 보여 1:1 그림의 양옆이 잘림, 유튜브는 오른쪽 아래에 영상 길이
const COVERED: Partial<Record<Purpose, { label: string; boxes: { left: number; top: number; width: number; height: number }[] }>> = {
  instagram: {
    label: "프로필 격자에서는 양옆이 잘려 보여요",
    boxes: [
      { left: 0, top: 0, width: 12.5, height: 100 },
      { left: 87.5, top: 0, width: 12.5, height: 100 },
    ],
  },
  youtube: {
    label: "오른쪽 아래는 영상 길이 표시에 가려요",
    boxes: [{ left: 86, top: 86, width: 12, height: 10 }],
  },
};

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
  const [copies, setCopies] = useState<string[]>([]);
  const [cutout, setCutout] = useState(false);
  // 배경을 지우고 다시 채운 그림 (이 브라우저에만). 비어 있으면 서버의 background_url
  const [bgSrc, setBgSrc] = useState("");
  const [showCovered, setShowCovered] = useState(false);

  useEffect(() => {
    setCopies(loadCopies(id));
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
      saveCopies(next.id, copies);
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

  const covered = g.input ? COVERED[g.input.purpose] : undefined;

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-h font-bold">다 만들었어요!</h1>

      <div className="relative">
      {cutout && g.background_url ? (
        <CutoutEditor
          photoUrl={g.background_url}
          name={`광고-${g.id.slice(0, 8)}.png`}
          cancelLabel="원래 그림 그대로 쓰기"
          onDone={(file) => {
            if (bgSrc) URL.revokeObjectURL(bgSrc);
            setBgSrc(URL.createObjectURL(file));
            setCutout(false);
            if (!edit) startEdit(g); // 지운 그림 위에 글자를 다시 얹어 보여 줌
          }}
          onCancel={() => setCutout(false)}
        />
      ) : edit && g.background_url ? (
        <TextCanvas src={bgSrc || g.background_url} state={edit} onChange={setEdit} canvasRef={canvasRef} />
      ) : (
        <div className="overflow-hidden rounded-card bg-mist shadow-sm">
          {/* eslint-disable-next-line @next/next/no-img-element -- 서버가 만든 최종 이미지 그대로 (프록시 경유) */}
          <img src={g.image_url} alt={g.message} width={g.width} height={g.height} className="block h-auto w-full" />
        </div>
      )}
        {/* 화면에만 보이는 표시. canvas 저장에는 안 들어감 */}
        {showCovered && !cutout &&
          covered?.boxes.map((b, i) => (
            <div
              key={i}
              aria-hidden
              className="pointer-events-none absolute bg-ink/50"
              style={{ left: `${b.left}%`, top: `${b.top}%`, width: `${b.width}%`, height: `${b.height}%` }}
            />
          ))}
      </div>

      {covered && !cutout && (
        <div className="-mt-4 flex flex-wrap items-center gap-3">
          <button type="button" className="btn-line" aria-pressed={showCovered} onClick={() => setShowCovered(!showCovered)}>
            {showCovered ? <EyeOff aria-hidden className="size-5" /> : <Eye aria-hidden className="size-5" />}
            {showCovered ? "가려지는 곳 숨기기" : "올리면 가려지는 곳 보기"}
          </button>
          {showCovered && <p className="hint">{covered.label}</p>}
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
          <TextEditor state={edit} copies={copies} onChange={setEdit} onReset={() => setEdit(null)} />
        ) : (
          <button type="button" className="btn-line" onClick={() => startEdit(g)}>
            <Pencil aria-hidden className="size-5" /> 글자 직접 고치기
          </button>
        ))}

      {g.background_url && !cutout && (
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" className="btn-line" onClick={() => setCutout(true)}>
            <Scissors aria-hidden className="size-5" /> 배경 지우고 색 채우기
          </button>
          {bgSrc && (
            <button type="button" className="btn-line" onClick={() => (URL.revokeObjectURL(bgSrc), setBgSrc(""))}>
              <Undo2 aria-hidden className="size-5" /> 원래 배경으로
            </button>
          )}
        </div>
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

      {g.parent_id && (
        <Link href={`/result/${g.parent_id}`} className="btn-line">
          <History aria-hidden className="size-5" /> 바로 전 결과로 돌아가기
        </Link>
      )}
      <Link href="/" className="btn-line">처음부터 새로 만들기</Link>
    </div>
  );
}


interface EditorProps {
  state: TextState;
  copies: string[];
  onChange: (s: TextState) => void;
  onReset: () => void;
}

/** 문구·스타일·크기. 위치는 미리보기에서 끌어서 (또는 방향키) */
function TextEditor({ state, copies, onChange, onReset }: EditorProps) {
  return (
    <section className="card flex flex-col gap-6">
      <h2 className="text-h-sm font-bold">글자 직접 고치기</h2>
      <p className="-mt-4 hint">그림은 그대로 두고 글자만 바꿔요. 위 이미지에서 글자를 끌어서 옮길 수 있어요.</p>
      <div>
        <label htmlFor="t" className="label">문구</label>
        <textarea id="t" rows={2} className="field" value={state.text} onChange={(e) => onChange({ ...state, text: e.target.value })} />
        <RiskyWords text={state.text} />
        {copies.length > 0 && (
          <div className="mt-3 flex flex-col gap-2" role="group" aria-label="추천받은 문구. 누르면 바로 얹어져요">
            {copies.map((c) => (
              <Chip key={c} on={state.text === c} onClick={() => onChange({ ...state, text: c })}>{c}</Chip>
            ))}
          </div>
        )}
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
