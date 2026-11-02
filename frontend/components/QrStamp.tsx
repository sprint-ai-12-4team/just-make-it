"use client";

import { Chip, FieldError } from "@/components/ui";
import { canvasOf } from "@/lib/cutout";
import { Loader2, QrCode } from "lucide-react";
import QRCode from "qrcode";
import { useState } from "react";

type Corner = "br" | "bl" | "tr" | "tl";
const CORNERS: { id: Corner; label: string }[] = [
  { id: "br", label: "오른쪽 아래" },
  { id: "bl", label: "왼쪽 아래" },
  { id: "tr", label: "오른쪽 위" },
  { id: "tl", label: "왼쪽 위" },
];

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

/** 그림 구석에 가게 QR을 붙임 (service_consulting.md G-2). 서버 API 추가 없음: 고친 그림 저장을 그대로 씀 */
export function QrStamp({ base, onSave }: { base: () => Promise<CanvasImageSource & { width: number; height: number }>; onSave: (image: HTMLCanvasElement, host: string) => Promise<void> }) {
  const [url, setUrl] = useState("");
  const [corner, setCorner] = useState<Corner>("br");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function stamp() {
    const link = linkOf(url);
    if (!link) return setError("가게 주소를 확인해 주세요. 예: naver.me/abcd");
    setBusy(true);
    setError("");
    try {
      const img = await base();
      const out = canvasOf(img.width, img.height);
      const ctx = out.getContext("2d")!;
      ctx.drawImage(img, 0, 0, img.width, img.height);
      // 짧은 변의 20%, 최소 160px. 흰 여백(4칸)까지 포함해야 카메라가 잘 읽음
      const size = Math.max(160, Math.round(Math.min(img.width, img.height) * 0.2));
      const qr = canvasOf(size, size);
      await QRCode.toCanvas(qr, link, { width: size, margin: 4, errorCorrectionLevel: "M", color: { dark: "#202020", light: "#ffffff" } });
      const pad = Math.round(Math.min(img.width, img.height) * 0.03);
      const x = corner.endsWith("r") ? img.width - size - pad : pad;
      const y = corner.startsWith("b") ? img.height - size - pad : pad;
      ctx.drawImage(qr, x, y);
      await onSave(out, new URL(link).hostname);
    } catch (e) {
      setError((e as Error).message || "QR을 넣지 못했어요. 다시 해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card flex flex-col gap-5">
      <h2 className="text-h-sm font-bold">가게 QR 넣기</h2>
      <p className="-mt-3 hint">손님이 휴대폰으로 찍으면 가게 페이지가 열려요. 전단지·포스터에 좋아요.</p>
      <div>
        <label htmlFor="qr-url" className="label">
          가게 링크
        </label>
        <input id="qr-url" type="url" inputMode="url" className="field" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="예: naver.me/abcd, 스마트스토어 주소" aria-invalid={!!error} aria-describedby="qr-err" />
        {error && <FieldError id="qr-err">{error}</FieldError>}
      </div>
      <fieldset>
        <legend className="label">넣을 곳</legend>
        <div className="flex flex-wrap gap-2">
          {CORNERS.map((c) => (
            <Chip key={c.id} on={corner === c.id} onClick={() => setCorner(c.id)}>
              {c.label}
            </Chip>
          ))}
        </div>
      </fieldset>
      <button type="button" className="btn-fill" disabled={busy || !url.trim()} onClick={stamp}>
        {busy ? <Loader2 aria-hidden className="size-5 animate-spin" /> : <QrCode aria-hidden className="size-5" />}
        {busy ? "넣는 중" : "QR 넣어서 저장"}
      </button>
      <p className="hint">넣은 뒤 휴대폰 카메라로 꼭 찍어 보세요. 글자를 다시 고치면 QR도 다시 넣어야 해요.</p>
    </section>
  );
}
