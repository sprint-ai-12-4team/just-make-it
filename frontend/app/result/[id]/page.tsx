"use client";

import { CutoutEditor } from "@/components/CutoutEditor";
import { CopyKit } from "@/components/CopyKit";
import { GenProgress } from "@/components/GenProgress";
import { QrOverlay, QrStamp, type QrPreview } from "@/components/QrStamp";
import { Shell } from "@/components/Shell";
import { StickyPreview } from "@/components/StickyPreview";
import { TextCanvas } from "@/components/TextCanvas";
import { Chip, Notice, RiskyWords, Waiting } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { canvasOf, placeOnScene } from "@/lib/cutout";
import { loadImage, save } from "@/lib/draw";
import { remember } from "@/lib/family";
import { drawText, FONTS, joinWords, loadCopies, loadFonts, POSITION_Y, saveCopies, splitWords, styleFor, TEXT_STYLES, type TextState, type WordState } from "@/lib/textStyles";
import { ADJUSTMENTS, IMAGE_MODELS, type Brief, type GenerateInput, type Generation, type ImageModel, type Purpose } from "@/lib/types";
import { Check, CloudUpload, Download, Eye, EyeOff, History, Link2, Loader2, Pencil, RefreshCw, Scissors, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/** 서버가 얹은 위치·크기·분위기 그대로의 글자 상태 */
function textOf(r: Generation): TextState {
  const l = r.text_layout;
  return { text: r.message, style: styleFor(r.input?.style).id, x: 0.5, y: POSITION_Y[l?.position ?? "top"], scale: l?.size_scale ?? 1 };
}

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

const pngOf = (c: HTMLCanvasElement) => new Promise<Blob>((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new Error("사진을 만들지 못했어요."))), "image/png"));

/** keep_product 결과: AI 장면 + 사용자 상품 + 글자를 합쳐 {글자 없는 그림, 최종 그림} (api_spec_next 4장) */
async function composeScene(g: Generation) {
  const [scene, product] = await Promise.all([loadImage(g.background_url!), loadImage(g.product_url!)]);
  const bg = placeOnScene(scene, product);
  const text = textOf(g);
  await loadFonts(text);
  const out = canvasOf(bg.width, bg.height);
  drawText(out, bg, text);
  return { bg, out, text };
}

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
  const [word, setWord] = useState<number | null>(null); // 단어별 편집 중 고른 단어
  const [picked, setPicked] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copies, setCopies] = useState<string[]>([]);
  const [cutout, setCutout] = useState(false);
  // 배경을 지우고 다시 채운 그림 (이 브라우저에만). 비어 있으면 서버의 background_url
  const [bgSrc, setBgSrc] = useState("");
  const [showCovered, setShowCovered] = useState(false);
  const [family, setFamily] = useState<{ id: string; img: string }[]>([]);
  const [familyFromServer, setFamilyFromServer] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [qr, setQr] = useState<QrPreview | null>(null); // 저장 전 그림 위에 얹어 보는 QR
  const [model, setModel] = useState<ImageModel | null>(null); // 다시 만들 때 그림 품질. null이면 처음 고른 것 (서버가 input에 안 돌려주면 빠르게)
  const composed = useRef(""); // 개발 모드에서 effect가 두 번 돌아도 한 번만 올림

  // 상담에서 왔으면 기획서의 채널·기간을 게시 문구 키트에 씀. 못 불러와도 그대로 동작
  const consultId = g?.input?.consult_id;
  useEffect(() => {
    if (consultId) api.getConsult(consultId).then((c) => setBrief(c.brief), () => {});
  }, [consultId]);

  useEffect(() => {
    setCopies(loadCopies(id));
    let alive = true;
    let timer = 0;
    // 만드는 중이면 2초마다 다시 조회 (api_spec V3). 잠깐 끊긴 연결(status 0)도 다시 시도
    const poll = () =>
      api
        .getGeneration(id)
        .then((r) => {
          if (!alive) return;
          setG(r);
          if (r.status === "processing") timer = window.setTimeout(poll, 2000);
          if (r.status === "success") loadFamily(r);
        })
        .catch((e) => {
          if (!alive) return;
          if (e instanceof ApiError && e.status === 0) timer = window.setTimeout(poll, 2000);
          else setError(e.message);
        });
    const loadFamily = (r: Generation) => {
      setFamily(remember(r.id, r.parent_id, r.image_url));
      // 서버 목록이 있으면 다른 기기에서 만든 것까지. 없으면(404) 이 브라우저 기록 그대로
      api
        .getFamily(r.id)
        .then((items) => {
          setFamily(items.map((f) => ({ id: f.id, img: f.image_url })));
          setFamilyFromServer(true);
        })
        .catch(() => {});
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id]);

  // 상품 그대로 + AI 장면: 처음 열 때 합쳐서 서버에 저장 → 이후 링크·글자 고치기·배경 지우기는 합친 그림으로
  useEffect(() => {
    if (g?.status !== "success" || !g.product_url || g.edited || !g.background_url || composed.current === g.id) return;
    composed.current = g.id;
    composeScene(g)
      .then(async ({ bg, out, text }) => {
        try {
          setG(await api.saveImage(g.id, await pngOf(out), await pngOf(bg), g.message));
        } catch {
          // 서버에 못 올려도 이 브라우저에서는 합친 그림으로 보여 주고 고칠 수 있게
          setBgSrc(URL.createObjectURL(await pngOf(bg)));
          setEdit(text);
        }
      })
      .catch((e) => {
        console.warn("상품 합치기 실패", e);
        setError("상품을 배경에 올리지 못했어요. 새로고침해 주세요.");
      });
  }, [g]);

  const startEdit = (r: Generation) => setEdit(textOf(r));

  /** 새로 만들기 시작 → 새 결과 화면에서 진행 상황을 봄 */
  async function start(input: GenerateInput) {
    setBusy(true);
    setError("");
    try {
      const next = await api.startGeneration(input);
      saveCopies(next, copies);
      router.push(`/result/${next}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  function remake(adjustments: string[]) {
    if (!g?.input) return;
    // 원본 사진은 서버가 parent_id로 다시 씀. 직접 고친 문구를 이어 씀 (g.input.message는 처음 입력값)
    const image_model = model ?? g.input.image_model ?? IMAGE_MODELS[0].id;
    api.logEvent(g.id, "remake", { adjustments, image_model });
    const message = edit?.text.trim() || g.message;
    start({ ...g.input, message, style: g.input.style ?? null, adjustments, parent_id: g.id, image_model });
  }

  async function copyLink() {
    await navigator.clipboard.writeText(location.href);
    api.logEvent(id, "copy_link");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  /** 고친 그림을 서버에 올려 링크로 연 사람도 같은 그림을 보게 함 */
  async function upload() {
    const canvas = canvasRef.current;
    if (!g || !edit || !canvas) return;
    setUploading(true);
    setError("");
    try {
      const image = await new Promise<Blob>((ok, no) => canvas.toBlob((b) => (b ? ok(b) : no(new Error("사진을 만들지 못했어요. 다시 해 주세요."))), "image/png"));
      const background = bgSrc ? await fetch(bgSrc).then((r) => r.blob()) : null;
      setG(await api.saveImage(g.id, image, background, edit.text.trim()));
      setEdit(null);
      if (bgSrc) URL.revokeObjectURL(bgSrc);
      setBgSrc("");
      setUploaded(true);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "아직 링크에 저장할 수 없어요. 내 기기에 저장해서 써 주세요." : (e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  /** QR 넣은 그림을 링크에 저장. 서버에 저장 기능이 없으면(404) 내 기기에 저장 */
  async function saveQr(out: HTMLCanvasElement, host: string) {
    if (!g) return;
    const message = edit?.text.trim() || g.message;
    const background = bgSrc ? await fetch(bgSrc).then((r) => r.blob()) : null;
    try {
      setG(await api.saveImage(g.id, await pngOf(out), background, message));
      setEdit(null);
      if (bgSrc) URL.revokeObjectURL(bgSrc);
      setBgSrc("");
      setUploaded(true);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) throw e;
      save(out, `광고-QR-${message.slice(0, 10)}.png`, setError);
      setError("아직 링크에 저장할 수 없어서 QR 넣은 그림을 내 기기에 저장했어요.");
    }
    api.logEvent(g.id, "add_qr", { host });
  }

  // 합치기 전 장면(상품 없음)이 잠깐 보이지 않게
  if (g?.status === "success" && g.product_url && !g.edited && !bgSrc && !error) return <Waiting title="상품을 배경에 올리고 있어요" hint="잠깐이면 돼요." />;
  if (busy) return <Waiting title="만들기를 시작했어요" hint="곧 진행 상황을 보여 드려요." />;
  if (!g)
    return error ? (
      <Notice
        action={
          <Link href="/" className="btn-fill">
            처음으로
          </Link>
        }
      >
        {error}
      </Notice>
    ) : (
      <div aria-busy className="aspect-square animate-pulse rounded-card bg-mist" />
    );

  if (g.status === "processing") return <GenProgress g={g} />;
  if (g.status === "error")
    return (
      <Notice
        action={
          g.input && (
            <button type="button" className="btn-fill" onClick={() => start({ ...g.input!, style: g.input!.style ?? null, parent_id: g.parent_id ?? null })}>
              <RefreshCw aria-hidden className="size-5" /> 다시 만들기
            </button>
          )
        }
      >
        그림을 만들지 못했어요. 잠시 후 다시 만들어 주세요.
      </Notice>
    );

  const covered = g.input ? COVERED[g.input.purpose] : undefined;
  const original = {
    label: "처음 만든 그림",
    // eslint-disable-next-line @next/next/no-img-element -- 서버가 만든 최종 이미지 그대로 (프록시 경유)
    node: <img src={g.image_url} alt={g.message} width={g.width} height={g.height} className="preview rounded-card bg-mist shadow-sm" />,
  };

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-h font-bold">다 만들었어요!</h1>

      {/* 넓은 화면: 그림 왼쪽 고정 + 설정 오른쪽. 좁은 화면: 내리면 그림이 서서히 줄어듦 (globals.css .page-wide) */}
      <div className={`page-wide flex flex-col gap-8 ${cutout ? "" : "lg:grid lg:grid-cols-2 lg:items-start lg:gap-10"}`}>
      {/* 좁은 화면은 contents: 미리보기의 sticky가 페이지 전체 기준으로 동작하게 */}
      <div className={`flex flex-col gap-4 max-lg:contents ${cutout ? "" : "lg:sticky lg:top-4"}`}>
      {cutout && g.background_url ? (
        <CutoutEditor
          photoUrl={g.background_url}
          name={`광고-${g.id.slice(0, 8)}.png`}
          cancelLabel="원래 그림 그대로 쓰기"
          text={edit ?? textOf(g)}
          compare={[original]}
          onDone={(file) => {
            if (bgSrc) URL.revokeObjectURL(bgSrc);
            setBgSrc(URL.createObjectURL(file));
            setCutout(false);
            if (!edit) startEdit(g); // 지운 그림 위에 글자를 다시 얹어 보여 줌
            api.logEvent(g.id, "cutout");
          }}
          onCancel={() => setCutout(false)}
        />
      ) : (
        <StickyPreview
          slides={[
            {
              label: edit ? "고치는 중" : "만든 그림",
              node: (
                // w-fit: 가려지는 곳 표시(%)가 그림 크기에 맞게
                <div className="relative mx-auto w-fit">
                  {edit && g.background_url ? <TextCanvas src={bgSrc || g.background_url} state={edit} onChange={setEdit} canvasRef={canvasRef} selected={word} onSelect={setWord} /> : original.node}
                  {/* 화면에만 보이는 표시. canvas 저장에는 안 들어감 */}
                  {showCovered &&
                    covered?.boxes.map((b, i) => (
                      <div key={i} aria-hidden className="pointer-events-none absolute bg-ink/50" style={{ left: `${b.left}%`, top: `${b.top}%`, width: `${b.width}%`, height: `${b.height}%` }} />
                    ))}
                  {qr && <QrOverlay place={qr} ratio={g.height / g.width} onMove={setQr} />}
                </div>
              ),
            },
            ...(edit ? [original] : []),
          ]}
        />
      )}

      {covered && !cutout && (
        <div className="flex flex-wrap max-lg:-mt-4 items-center gap-3">
          <button type="button" className="btn-line" aria-pressed={showCovered} onClick={() => setShowCovered(!showCovered)}>
            {showCovered ? <EyeOff aria-hidden className="size-5" /> : <Eye aria-hidden className="size-5" />}
            {showCovered ? "가려지는 곳 숨기기" : "올리면 가려지는 곳 보기"}
          </button>
          {showCovered && <p className="hint">{covered.label}</p>}
        </div>
      )}
      </div>

      <div className="flex min-w-0 flex-col gap-8">

      {/* 배경 지우는 중에는 저장·글자 고치기를 숨김: 미리보기가 배경 지우기 화면이라 눌러도 반영이 안 보임 */}
      {!cutout && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {edit ? (
              <button type="button" className="btn-fill" onClick={() => (save(canvasRef.current, `광고-${edit.text.slice(0, 10)}.png`, setError), api.logEvent(g.id, "download", { edited: true }))}>
                <Download aria-hidden className="size-5" /> 내 기기에 저장
              </button>
            ) : (
              // 프록시 덕분에 같은 출처라 download 속성이 동작
              <a className="btn-fill" href={g.image_url} download={`광고-${g.message.slice(0, 10)}.png`} onClick={() => api.logEvent(g.id, "download", { edited: !!g.edited })}>
                <Download aria-hidden className="size-5" /> 내 기기에 저장
              </a>
            )}
            <button type="button" className="btn-line" onClick={copyLink} aria-live="polite">
              {copied ? <Check aria-hidden className="size-5" /> : <Link2 aria-hidden className="size-5" />}
              {copied ? "링크를 복사했어요" : "링크 복사"}
            </button>
          </div>

          {edit && (
            <div className="flex flex-col gap-2">
              <button type="button" className="btn-line" disabled={uploading} onClick={upload}>
                {uploading ? <Loader2 aria-hidden className="size-5 animate-spin" /> : <CloudUpload aria-hidden className="size-5" />}
                {uploading ? "저장하는 중" : "고친 그림을 링크에도 저장"}
              </button>
              <p className="hint">저장하면 링크를 받은 사람도 고친 그림을 봐요.</p>
            </div>
          )}
          {uploaded && !edit && (
            <p role="status" className="-mt-4 hint">
              고친 그림을 저장했어요. 이제 링크로도 이 그림이 보여요.
            </p>
          )}

          {error && <Notice>{error}</Notice>}

          {/* 원본이 없는 예전 결과는 직접 고치기 불가 */}
          {g.background_url &&
            (edit ? (
              <TextEditor
                state={edit}
                copies={copies}
                selected={word}
                onSelect={setWord}
                onChange={setEdit}
                onSplit={() => canvasRef.current && (setEdit(splitWords(canvasRef.current.width, canvasRef.current.height, edit)), setWord(null))}
                onReset={() => (setEdit(null), setWord(null))}
              />
            ) : (
              <button type="button" className="btn-line" onClick={() => (startEdit(g), api.logEvent(g.id, "edit_text"))}>
                <Pencil aria-hidden className="size-5" /> 글자 직접 고치기
              </button>
            ))}
        </>
      )}

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

      {!cutout && (
        <>
          <QrStamp base={() => (edit && canvasRef.current ? Promise.resolve(canvasRef.current) : loadImage(g.image_url))} ratio={g.height / g.width} place={qr} onPlace={setQr} onSave={saveQr} />
          <CopyKit key={brief ? "brief" : "plain"} gid={g.id} text={edit?.text.trim() || g.message} productName={g.input?.product_name} brief={brief} />
        </>
      )}

      <section className="card flex flex-col gap-6">
        <h2 className="text-h-sm font-bold">그림이 마음에 안 드세요?</h2>
        <fieldset>
          <legend className="label">이렇게 바꿔 주세요 (여러 개 골라도 돼요)</legend>
          <div className="flex flex-wrap gap-2">
            {ADJUSTMENTS.map((a) => (
              <Chip key={a} on={picked.includes(a)} onClick={() => setPicked(picked.includes(a) ? picked.filter((x) => x !== a) : [...picked, a])}>
                {a}
              </Chip>
            ))}
          </div>
        </fieldset>
        {g.input && (
          <fieldset>
            <legend className="label">그림 품질</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {IMAGE_MODELS.map((m) => {
                const on = (model ?? g.input!.image_model ?? IMAGE_MODELS[0].id) === m.id;
                return (
                  <button key={m.id} type="button" aria-pressed={on} onClick={() => setModel(m.id)} className={`rounded-card border-2 p-4 text-left ${on ? "border-ink bg-pollen" : "border-mist bg-white hover:border-charcoal"}`}>
                    <span className="block font-semibold">{m.title}</span>
                    <span className="hint">{m.desc}</span>
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" className="btn-fill" disabled={!picked.length} onClick={() => remake(picked)}>
            고른 대로 다시 만들기
          </button>
          <button type="button" className="btn-line" onClick={() => remake([])}>
            <RefreshCw aria-hidden className="size-5" /> 그냥 한 번 더 만들기
          </button>
        </div>
      </section>

      {family.length > 1 && (
        <section className="card flex flex-col gap-4">
          <h2 className="text-h-sm font-bold">같은 원본에서 만든 결과</h2>
          <p className="-mt-2 hint">{familyFromServer ? "" : "이 브라우저에서 만든 것만 보여요. "}눌러서 그 결과로 돌아갈 수 있어요.</p>
          <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4">
            {family.map((f, i) => (
              <li key={f.id}>
                <Link
                  href={`/result/${f.id}`}
                  aria-current={f.id === g.id ? "page" : undefined}
                  className={`block overflow-hidden rounded-btn border-2 ${f.id === g.id ? "border-ink" : "border-mist hover:border-charcoal"}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- 작은 미리보기 */}
                  <img src={f.img} alt={`${i + 1}번째 결과${f.id === g.id ? " (지금 보는 것)" : ""}`} className="block aspect-square w-full object-cover" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      {g.parent_id && (
        <Link href={`/result/${g.parent_id}`} className="btn-line">
          <History aria-hidden className="size-5" /> 바로 전 결과로 돌아가기
        </Link>
      )}
      <Link href="/" className="btn-line">
        처음부터 새로 만들기
      </Link>
      </div>
      </div>
    </div>
  );
}

interface EditorProps {
  state: TextState;
  copies: string[];
  selected: number | null;
  onSelect: (i: number | null) => void;
  onChange: (s: TextState) => void;
  onSplit: () => void;
  onReset: () => void;
}

/** 스타일(효과)·글꼴·색·크기 고르기. 전체용과 단어용이 같이 씀 */
function Look({ id, style, font, color, scale, range, onPatch }: {
  id: string;
  style: string;
  font?: string;
  color?: string;
  scale: number;
  range: [number, number];
  onPatch: (p: { style?: string; font?: string; color?: string; scale?: number }) => void;
}) {
  const st = TEXT_STYLES.find((s) => s.id === style) ?? TEXT_STYLES[0];
  return (
    <>
      <fieldset>
        <legend className="label">글자 스타일 (글꼴·색·테두리·그림자 묶음)</legend>
        <div className="flex flex-wrap gap-2">
          {TEXT_STYLES.map((s) => (
            <Chip key={s.id} on={style === s.id} onClick={() => onPatch({ style: s.id, font: undefined, color: undefined })}>
              <span style={{ fontFamily: `"${s.font}"` }}>{s.name}</span>
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="label">글꼴</legend>
        <div className="flex flex-wrap gap-2">
          {FONTS.map((f) => (
            <Chip key={f.id} on={(font ?? st.font) === f.id} onClick={() => onPatch({ font: f.id })}>
              <span style={{ fontFamily: `"${f.id}"` }}>{f.name}</span>
            </Chip>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor={`${id}-color`} className="label mb-0">
          글자 색
        </label>
        <input id={`${id}-color`} type="color" value={color ?? "#ffffff"} onChange={(e) => onPatch({ color: e.target.value })} className="h-11 w-16 cursor-pointer rounded-btn border-2 border-mist" />
        {color && (
          <button type="button" className="btn-line min-h-[44px] px-4" onClick={() => onPatch({ color: undefined })}>
            스타일 색으로
          </button>
        )}
      </div>
      <div>
        <label htmlFor={`${id}-size`} className="label">
          글자 크기
        </label>
        <input id={`${id}-size`} type="range" min={range[0]} max={range[1]} step={0.05} value={scale} onChange={(e) => onPatch({ scale: Number(e.target.value) })} className="w-full accent-ink" />
      </div>
    </>
  );
}

/** 문구·스타일·글꼴·색·크기. 위치는 미리보기에서 끌어서 (또는 방향키). 단어별로 나누면 단어마다 따로 */
function TextEditor({ state, copies, selected, onSelect, onChange, onSplit, onReset }: EditorProps) {
  const words = state.words;
  const w = words && selected !== null ? words[selected] : null;
  const setWords = (next: WordState[]) => onChange({ ...state, words: next, text: joinWords(next) });
  const patchWord = (p: Partial<WordState>) => words && selected !== null && setWords(words.map((x, i) => (i === selected ? { ...x, ...p } : x)));
  // 전체에 한꺼번에: 단어마다 따로 고친 같은 항목은 지움 (크기는 단어 크기에 곱함)
  const patchAll = (p: Partial<TextState>) => {
    const clear = Object.keys(p).filter((k) => k !== "scale");
    onChange({ ...state, ...p, words: words?.map((x) => ({ ...x, ...Object.fromEntries(clear.map((k) => [k, undefined])) })) });
  };

  return (
    <section className="card flex flex-col gap-6">
      <h2 className="text-h-sm font-bold">글자 직접 고치기</h2>
      <p className="-mt-4 hint">그림은 그대로 두고 글자만 바꿔요. 위 이미지에서 글자를 끌어서 옮길 수 있어요.</p>

      <div className="grid grid-cols-2 gap-2" role="group" aria-label="고치는 방법">
        <button type="button" aria-pressed={!words} className={!words ? "btn-fill" : "btn-line"} onClick={() => words && (onChange({ ...state, words: undefined }), onSelect(null))}>
          문구 전체
        </button>
        <button type="button" aria-pressed={!!words} className={words ? "btn-fill" : "btn-line"} onClick={() => !words && onSplit()}>
          단어별로
        </button>
      </div>

      {!words ? (
        <div>
          <label htmlFor="t" className="label">
            문구
          </label>
          <textarea id="t" rows={2} className="field" value={state.text} onChange={(e) => onChange({ ...state, text: e.target.value })} />
          <RiskyWords text={state.text} />
          {copies.length > 0 && (
            <div className="mt-3 flex flex-col gap-2" role="group" aria-label="추천받은 문구. 누르면 바로 얹어져요">
              {copies.map((c) => (
                <Chip key={c} on={state.text === c} onClick={() => onChange({ ...state, text: c })}>
                  {c}
                </Chip>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="hint">고칠 단어를 고르세요. 위 이미지에서 단어를 눌러도 돼요. 빈 곳을 끌면 전체가 같이 움직여요.</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="단어 고르기">
            {words.map((x, i) => (
              <Chip key={i} on={selected === i} onClick={() => onSelect(selected === i ? null : i)}>
                {x.text || "(빈 단어)"}
              </Chip>
            ))}
          </div>
          <RiskyWords text={state.text} />
        </div>
      )}

      {w && (
        <div className="flex flex-col gap-6 rounded-card border-2 border-ink p-5">
          <h3 className="font-bold">‘{w.text}’만 고치기</h3>
          <div>
            <label htmlFor="w-text" className="label">
              단어
            </label>
            <input id="w-text" className="field" value={w.text} onChange={(e) => patchWord({ text: e.target.value })} />
            <p className="mt-2 hint">지우면 이 단어가 빠져요.</p>
          </div>
          <Look id="w" style={w.style ?? state.style} font={w.font ?? state.font} color={w.color ?? state.color} scale={w.scale ?? 1} range={[0.4, 2.5]} onPatch={patchWord} />
          <button type="button" className="btn-line" onClick={() => patchWord({ style: undefined, font: undefined, color: undefined, scale: undefined })}>
            <Undo2 aria-hidden className="size-5" /> 이 단어 모양을 전체와 같게
          </button>
        </div>
      )}

      {words && <h3 className="-mb-2 font-bold">전체에 한꺼번에</h3>}
      <Look id="all" style={state.style} font={state.font} color={state.color} scale={state.scale} range={[0.6, 1.6]} onPatch={patchAll} />

      <button type="button" className="btn-line" onClick={onReset}>
        <Undo2 aria-hidden className="size-5" /> 처음 이미지로 돌아가기
      </button>
    </section>
  );
}
