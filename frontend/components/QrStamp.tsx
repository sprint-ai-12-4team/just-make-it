"use client";

import { Chip, FieldError } from "@/components/ui";
import { canvasOf } from "@/lib/cutout";
import { clampPlace, qrCanvas, type QrLogo, type QrLook, type QrPlace } from "@/lib/qr";
import { Eye, Loader2, QrCode, X } from "lucide-react";
import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

/** 그림 위에 미리 얹은 QR. src는 화면용 작은 그림 */
export type QrPreview = QrPlace & { src: string };

type Corner = "br" | "bl" | "tr" | "tl";
const CORNERS: { id: Corner; label: string }[] = [
  { id: "br", label: "오른쪽 아래" },
  { id: "bl", label: "왼쪽 아래" },
  { id: "tr", label: "오른쪽 위" },
  { id: "tl", label: "왼쪽 위" },
];
// 테두리 색 빠른 선택 (DESIGN.md 팔레트). 다른 색은 색 고르기로
const BORDERS = [
  { color: "#202020", label: "먹색" },
  { color: "#ffdb5b", label: "꿀색" },
  { color: "#3b3b3b", label: "숯색" },
];
const EMOJIS = ["☕", "🍞", "🍰", "🌸", "💛", "🛍️"];

/** 주소 확인: 앞에 https://가 없으면 붙이고, http·https만 받음 (javascript: 등 차단) */
export function linkOf(v: string): string | null {
  const s = v.trim();
  if (!s) return null;
  try {
    const u = new URL(/^[a-z][a-z0-9+.-]*:/i.test(s) ? s : `https://${s}`);
    return (u.protocol === "https:" || u.protocol === "http:") && u.hostname.includes(".") ? u.href : null;
  } catch {
    return null;
  }
}

/** 미리보기 그림 위 QR. 끌거나 방향키로 옮김. 부모가 그림 크기와 같은 relative 상자여야 함 */
export function QrOverlay({ place, ratio, onMove }: { place: QrPreview; ratio: number; onMove: (p: QrPreview) => void }) {
  const drag = useRef<{ px: number; py: number; x: number; y: number; W: number; H: number } | null>(null);
  const move = (x: number, y: number) => onMove(clampPlace({ ...place, x, y }, ratio));
  const KEYS: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  return (
    // eslint-disable-next-line @next/next/no-img-element -- 브라우저에서 그린 QR 미리보기
    <img
      src={place.src}
      alt="가게 QR 미리보기. 끌거나 방향키로 옮길 수 있어요"
      tabIndex={0}
      draggable={false}
      className="absolute cursor-move touch-none select-none drop-shadow-[0_1px_8px_rgba(32,32,32,0.12)]"
      style={{ left: `${place.x * 100}%`, top: `${place.y * 100}%`, width: `${place.w * 100}%` }}
      onPointerDown={(e) => {
        const box = e.currentTarget.parentElement!.getBoundingClientRect();
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { px: e.clientX, py: e.clientY, x: place.x, y: place.y, W: box.width, H: box.height };
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (d) move(d.x + (e.clientX - d.px) / d.W, d.y + (e.clientY - d.py) / d.H);
      }}
      onPointerUp={() => (drag.current = null)}
      onPointerCancel={() => (drag.current = null)}
      onKeyDown={(e) => {
        const k = KEYS[e.key];
        if (!k) return;
        e.preventDefault();
        move(place.x + k[0] * 0.01, place.y + k[1] * 0.01);
      }}
    />
  );
}

/**
 * 가게 QR: 먼저 그림 위에 얹어 보고(끌어서 옮김) 마음에 들면 저장 (service_consulting.md G-2).
 * 서버 API 추가 없음: 고친 그림 저장을 그대로 씀. ratio = 그림 세로/가로
 */
export function QrStamp({
  base,
  ratio,
  place,
  onPlace,
  onSave,
}: {
  base: () => Promise<CanvasImageSource & { width: number; height: number }>;
  ratio: number;
  place: QrPreview | null;
  onPlace: Dispatch<SetStateAction<QrPreview | null>>;
  onSave: (image: HTMLCanvasElement, host: string) => Promise<void>;
}) {
  const [url, setUrl] = useState("");
  const [corner, setCorner] = useState<Corner>("br");
  const [size, setSize] = useState(0.2); // 짧은 변 대비
  const [round, setRound] = useState(false);
  const [border, setBorder] = useState(BORDERS[0].color);
  const [logo, setLogo] = useState<QrLogo>({ kind: "none" });
  const [emoji, setEmoji] = useState(EMOJIS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const link = linkOf(url);
  const look: QrLook = { round, border, logo: logo.kind === "emoji" ? { kind: "emoji", text: emoji } : logo };
  const lookKey = JSON.stringify(look);
  const w = size * Math.min(1, ratio); // 그림 너비 대비
  const showing = !!place;

  function cornerPlace(c: Corner, qw: number): QrPlace {
    const px = 0.03 * Math.min(1, ratio);
    const py = 0.03 * Math.min(1, 1 / ratio);
    return { x: c.endsWith("r") ? 1 - qw - px : px, y: c.startsWith("b") ? 1 - qw / ratio - py : py, w: qw };
  }

  // 얹어 둔 채로 주소·모양·크기를 바꾸면 미리보기도 바로 다시 그림 (위치는 그대로)
  useEffect(() => {
    if (!showing || !link) return;
    let alive = true;
    qrCanvas(link, JSON.parse(lookKey), 360)
      .then((c) => alive && onPlace((p) => p && clampPlace({ ...p, w, src: c.toDataURL() }, ratio)))
      .catch((e) => alive && setError((e as Error).message));
    return () => {
      alive = false;
    };
  }, [showing, link, lookKey, w, ratio, onPlace]);

  async function preview() {
    if (!link) return setError("가게 주소를 확인해 주세요. 예: naver.me/abcd");
    setError("");
    try {
      const c = await qrCanvas(link, look, 360);
      onPlace({ ...cornerPlace(corner, w), src: c.toDataURL() });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function stamp() {
    if (!link || !place) return;
    setBusy(true);
    setError("");
    try {
      const img = await base();
      const out = canvasOf(img.width, img.height);
      const ctx = out.getContext("2d")!;
      ctx.drawImage(img, 0, 0, img.width, img.height);
      const qr = await qrCanvas(link, look, Math.round(place.w * img.width));
      ctx.drawImage(qr, Math.round(place.x * img.width), Math.round(place.y * img.height));
      await onSave(out, new URL(link).hostname);
      onPlace(null);
    } catch (e) {
      setError((e as Error).message || "QR을 넣지 못했어요. 다시 해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  function pickFile(f: File | undefined) {
    if (!f) return;
    if (logo.kind === "image") URL.revokeObjectURL(logo.src);
    setLogo({ kind: "image", src: URL.createObjectURL(f) });
  }

  return (
    <section className="card flex flex-col gap-6">
      <h2 className="text-h-sm font-bold">가게 QR 넣기</h2>
      <p className="-mt-4 hint">손님이 휴대폰으로 찍으면 가게 페이지가 열려요. 먼저 그림 위에 얹어 보고, 끌어서 자리를 잡은 뒤 저장해요.</p>
      <div>
        <label htmlFor="qr-url" className="label">
          가게 링크
        </label>
        <input id="qr-url" type="url" inputMode="url" className="field" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="예: naver.me/abcd, 스마트스토어 주소" aria-invalid={!!error} aria-describedby="qr-err" />
        {error && <FieldError id="qr-err">{error}</FieldError>}
      </div>

      <fieldset>
        <legend className="label">넣을 곳</legend>
        <p className="-mt-1 mb-3 hint">얹은 뒤에는 그림 위 QR을 직접 끌어서 옮겨도 돼요.</p>
        <div className="flex flex-wrap gap-2">
          {CORNERS.map((c) => (
            <Chip key={c.id} on={corner === c.id} onClick={() => (setCorner(c.id), onPlace((p) => p && { ...p, ...cornerPlace(c.id, p.w) }))}>
              {c.label}
            </Chip>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor="qr-size" className="label">
          크기 <span className="hint">짧은 변의 {Math.round(size * 100)}%</span>
        </label>
        <input id="qr-size" type="range" min={0.15} max={0.35} step={0.01} value={size} onChange={(e) => setSize(Number(e.target.value))} className="w-full accent-ink" />
      </div>

      <fieldset>
        <legend className="label">점 모양</legend>
        <div className="flex flex-wrap gap-2">
          <Chip on={!round} onClick={() => setRound(false)}>
            네모
          </Chip>
          <Chip on={round} onClick={() => setRound(true)}>
            동그라미
          </Chip>
        </div>
      </fieldset>

      <fieldset>
        <legend className="label">테두리 색</legend>
        <div className="flex flex-wrap items-center gap-2">
          {BORDERS.map((b) => (
            <Chip key={b.color} on={border === b.color} onClick={() => setBorder(b.color)}>
              <span aria-hidden className="size-4 rounded-full border border-charcoal" style={{ background: b.color }} /> {b.label}
            </Chip>
          ))}
          <label className="chip cursor-pointer">
            <input type="color" value={border} onChange={(e) => setBorder(e.target.value)} className="size-5 cursor-pointer rounded-full border-0 bg-transparent p-0" />
            다른 색
          </label>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="label">가운데 로고</legend>
        <div className="flex flex-wrap gap-2">
          <Chip on={logo.kind === "none"} onClick={() => setLogo({ kind: "none" })}>
            없음
          </Chip>
          <Chip on={logo.kind === "emoji"} onClick={() => setLogo({ kind: "emoji", text: emoji })}>
            이모지·글자
          </Chip>
          <label className={`chip cursor-pointer ${logo.kind === "image" ? "chip-on" : ""}`}>
            <input type="file" accept="image/svg+xml,image/png,image/webp" className="sr-only" onChange={(e) => pickFile(e.target.files?.[0])} />
            {logo.kind === "image" ? "로고 바꾸기" : "로고 파일 (SVG·PNG)"}
          </label>
        </div>
        {logo.kind === "emoji" && (
          <div className="flex flex-wrap items-center gap-2">
            {EMOJIS.map((x) => (
              <Chip key={x} on={emoji === x} onClick={() => setEmoji(x)}>
                <span className="text-sub">{x}</span>
              </Chip>
            ))}
            <label htmlFor="qr-emoji" className="sr-only">
              직접 입력 (짧게)
            </label>
            <input id="qr-emoji" className="field w-28" value={emoji} maxLength={4} onChange={(e) => setEmoji(e.target.value)} placeholder="직접 입력" />
          </div>
        )}
        {logo.kind !== "none" && <p className="hint">로고를 넣으면 QR을 더 촘촘하게 만들어 가려져도 읽혀요. 그래도 저장 전에 꼭 찍어 보세요.</p>}
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        {place ? (
          <>
            <button type="button" className="btn-fill" disabled={busy || !link} onClick={stamp}>
              {busy ? <Loader2 aria-hidden className="size-5 animate-spin" /> : <QrCode aria-hidden className="size-5" />}
              {busy ? "넣는 중" : "이대로 넣어서 저장"}
            </button>
            <button type="button" className="btn-line" disabled={busy} onClick={() => onPlace(null)}>
              <X aria-hidden className="size-5" /> QR 빼기
            </button>
          </>
        ) : (
          <button type="button" className="btn-fill sm:col-span-2" disabled={!url.trim()} onClick={preview}>
            <Eye aria-hidden className="size-5" /> 그림 위에 얹어 보기
          </button>
        )}
      </div>
      <p className="hint">넣은 뒤 휴대폰 카메라로 꼭 찍어 보세요. 글자를 다시 고치면 QR도 다시 넣어야 해요.</p>
    </section>
  );
}
