// 가게 QR 그리기: 둥근 바탕 + 테두리 + (점 모양) + (가운데 이모지·로고)
import QRCode from "qrcode";

export type QrLogo = { kind: "none" } | { kind: "emoji"; text: string } | { kind: "image"; src: string };
export interface QrLook {
  round: boolean; // 점을 동그랗게
  border: string; // 테두리 색
  logo: QrLogo;
}
/** 그림 대비 비율. x·y는 QR 왼쪽 위, w는 그림 너비 대비 QR 한 변 */
export interface QrPlace {
  x: number;
  y: number;
  w: number;
}

const INK = "#202020";
const QUIET = 3; // 흰 여백 칸 수 (표준 4칸, 둥근 바탕·테두리가 경계를 만들어 줘서 3칸으로)

/** 모서리 세 곳의 위치 찾기 무늬(7x7) 안인지 */
export const inFinder = (r: number, c: number, n: number) => (r < 7 || r >= n - 7) && (c < 7 || c >= n - 7) && !(r >= n - 7 && c >= n - 7);

/**
 * 가운데 로고 자리 칸 수. 홀수여야 가운데 정렬 (n도 항상 홀수). 오류 복구 H(30%) 안
 * 실측(BarcodeDetector, 짧은·긴 링크 × 네모·동그라미 × 160·360px): 한 변 36%까지 읽힘, 40%부터 짧은 링크 실패.
 * 카메라 흔들림·인쇄 여유로 32%
 */
export const logoCells = (n: number) => {
  const k = Math.round(n * 0.32);
  return k % 2 ? k : k + 1;
};

/** 그림 밖으로 안 나가게. ratio = 그림 세로/가로 */
export const clampPlace = <T extends QrPlace>(p: T, ratio: number): T => ({
  ...p,
  x: Math.min(Math.max(p.x, 0), 1 - p.w),
  y: Math.min(Math.max(p.y, 0), 1 - p.w / ratio),
});

function box(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, r: number, color: string) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x, y, s, s, r);
  ctx.fill();
}

function loadLocal(src: string) {
  return new Promise<HTMLImageElement>((ok, no) => {
    const img = new Image();
    img.onload = () => ok(img);
    img.onerror = () => no(new Error("로고 그림을 열지 못했어요. 다른 파일로 해 주세요."));
    img.src = src;
  });
}

export async function qrCanvas(link: string, look: QrLook, size: number): Promise<HTMLCanvasElement> {
  const hasLogo = look.logo.kind !== "none";
  const { modules } = QRCode.create(link, { errorCorrectionLevel: hasLogo ? "H" : "M" });
  const n = modules.size;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;

  // 바탕: 둥근 모서리 + 테두리 (화면에서 축소돼도 2px 안팎으로 보이게 크기에 비례)
  const bw = Math.max(2, Math.round(size * 0.02));
  const radius = size * 0.12;
  box(ctx, 0, 0, size, radius, look.border);
  box(ctx, bw, bw, size - bw * 2, radius - bw, "#ffffff");

  // 한 칸을 정수 px로 해야 칸 사이 틈이 안 생김
  const m = Math.floor((size - bw * 2) / (n + QUIET * 2));
  const o = (size - n * m) / 2;
  const k = hasLogo ? logoCells(n) : 0;
  const st = (n - k) / 2;
  const inLogo = (r: number, col: number) => k > 0 && r >= st && r < st + k && col >= st && col < st + k;

  ctx.fillStyle = INK;
  for (let r = 0; r < n; r++)
    for (let col = 0; col < n; col++) {
      if (!modules.get(r, col) || inFinder(r, col, n) || inLogo(r, col)) continue;
      if (look.round) {
        ctx.beginPath();
        ctx.arc(o + (col + 0.5) * m, o + (r + 0.5) * m, m * 0.45, 0, Math.PI * 2);
        ctx.fill();
      } else ctx.fillRect(o + col * m, o + r * m, m, m);
    }

  // 위치 찾기 무늬는 점으로 쪼개지 않고 덩어리로 (카메라가 잘 찾게)
  const cr = look.round ? m : 0;
  for (const [fr, fc] of [[0, 0], [0, n - 7], [n - 7, 0]]) {
    const x = o + fc * m;
    const y = o + fr * m;
    ctx.save();
    ctx.translate(x, y);
    box(ctx, 0, 0, 7 * m, cr * 2, INK);
    box(ctx, m, m, 5 * m, cr * 1.4, "#ffffff");
    box(ctx, 2 * m, 2 * m, 3 * m, cr, INK);
    ctx.restore();
  }

  if (look.logo.kind !== "none") {
    const s = k * m;
    const cx = size / 2;
    if (look.logo.kind === "emoji") {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      let px = Math.round(s * 0.9);
      const font = (p: number) => `700 ${p}px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji","Pretendard Variable",sans-serif`;
      ctx.font = font(px);
      const w = ctx.measureText(look.logo.text).width;
      if (w > s * 0.9) ctx.font = font((px = Math.floor((px * s * 0.9) / w)));
      ctx.fillStyle = INK;
      ctx.fillText(look.logo.text, cx, cx + px * 0.05);
    } else {
      const img = await loadLocal(look.logo.src);
      // 크기 정보가 없는 SVG는 정사각형으로
      const iw = img.width || s;
      const ih = img.height || s;
      const fit = Math.min((s * 0.9) / iw, (s * 0.9) / ih);
      const w = iw * fit;
      const h = ih * fit;
      ctx.drawImage(img, cx - w / 2, cx - h / 2, w, h);
    }
  }
  return c;
}
