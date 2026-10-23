// 글자 직접 고치기: 글자 없는 원본(background_url) 위에 문구를 <canvas>로 얹음.
// 1~5번은 core/text_overlay.py DESIGNS를 옮긴 것 (서버가 처음 얹는 디자인과 같은 계열). 크기·두께는 이미지 가로 대비 비율
import { wrap } from "./draw";

type Rgb = string;
export interface TextStyle {
  id: string;
  name: string;
  font: string; // globals.css @font-face 이름
  size: number;
  maxWidth: number;
  align: "center" | "left";
  tracking: number;
  fill: Rgb | "auto" | "gold" | "none"; // auto·gold: 배경 밝기에 따라 색을 고름
  stroke?: [Rgb, number];
  depth?: [Rgb, number, number]; // 입체 그림자 (색, x, y)
  shadow?: [Rgb, number, number]; // 흐린 그림자 (색, 흐림, y)
  glow?: Rgb;
  back?: ["box" | "band" | "highlight", Rgb]; // 글자 뒤 바탕
  deco?: "sparkle" | "wave" | "rules" | "accent";
  decoColor?: Rgb | "same";
  rotate: number;
  shear: number;
}

export const TEXT_STYLES: TextStyle[] = [
  { id: "pop", name: "톡톡 팝", font: "Jua", size: 0.13, maxWidth: 0.72, align: "center", tracking: 0, fill: "#fff",
    stroke: ["rgb(232,84,120)", 0.09], depth: ["rgb(150,40,75)", 0, 0.07], shadow: ["rgba(0,0,0,.43)", 0.08, 0.12],
    deco: "sparkle", decoColor: "rgb(255,226,110)", rotate: -3, shear: 0 },
  { id: "warm", name: "따뜻한 손글씨", font: "YeonSung", size: 0.12, maxWidth: 0.74, align: "center", tracking: 0, fill: "rgb(255,247,232)",
    stroke: ["rgb(122,72,40)", 0.06], shadow: ["rgba(90,50,25,.67)", 0.12, 0.05], deco: "wave", decoColor: "rgb(255,236,205)", rotate: -2, shear: 0 },
  { id: "gold", name: "고급 골드", font: "GowunBatang", size: 0.085, maxWidth: 0.7, align: "center", tracking: 0.12, fill: "gold",
    shadow: ["rgba(0,0,0,.47)", 0.06, 0.03], deco: "rules", decoColor: "same", rotate: 0, shear: 0 },
  { id: "simple", name: "깔끔 미니멀", font: "GowunDodum", size: 0.075, maxWidth: 0.5, align: "left", tracking: 0.02, fill: "auto",
    shadow: ["rgba(0,0,0,.24)", 0.05, 0.02], deco: "accent", decoColor: "same", rotate: 0, shear: 0 },
  { id: "impact", name: "강렬 임팩트", font: "BlackHanSans", size: 0.14, maxWidth: 0.78, align: "center", tracking: 0, fill: "rgb(255,232,60)",
    stroke: ["rgb(20,20,20)", 0.08], depth: ["rgb(205,25,25)", 0.06, 0.06], shadow: ["rgba(0,0,0,.55)", 0.06, 0.1], rotate: -4, shear: 0.18 },
  { id: "sale", name: "세일 스티커", font: "BlackHanSans", size: 0.11, maxWidth: 0.7, align: "center", tracking: 0.02, fill: "#fff",
    back: ["box", "rgb(232,52,58)"], shadow: ["rgba(0,0,0,.35)", 0.1, 0.08], rotate: -6, shear: 0 },
  { id: "band", name: "띠 배너", font: "GowunDodum", size: 0.07, maxWidth: 0.88, align: "center", tracking: 0.02, fill: "#fff",
    back: ["band", "rgba(32,32,32,.62)"], rotate: 0, shear: 0 },
  { id: "neon", name: "네온사인", font: "Jua", size: 0.11, maxWidth: 0.74, align: "center", tracking: 0.02, fill: "#fff",
    stroke: ["rgb(255,79,216)", 0.025], glow: "rgb(255,79,216)", rotate: 0, shear: 0 },
  { id: "marker", name: "형광펜", font: "GowunDodum", size: 0.08, maxWidth: 0.7, align: "center", tracking: 0, fill: "rgb(34,34,34)",
    back: ["highlight", "rgba(255,226,60,.92)"], rotate: -1, shear: 0 },
  { id: "outline", name: "외곽선", font: "BlackHanSans", size: 0.13, maxWidth: 0.78, align: "center", tracking: 0.02, fill: "none",
    stroke: ["#fff", 0.03], shadow: ["rgba(0,0,0,.5)", 0.06, 0.04], rotate: 0, shear: 0 },
];

// 서버 분위기 칩 → 처음 보여줄 스타일 (서버가 얹은 디자인과 같은 것)
const MOOD_STYLE: Record<string, string> = {
  "밝고 경쾌한": "pop", 따뜻한: "warm", 고급스러운: "gold", 심플한: "simple", 강렬한: "impact",
};
export const styleFor = (mood?: string | null) => TEXT_STYLES.find((s) => s.id === MOOD_STYLE[mood ?? ""]) ?? TEXT_STYLES[0];

/** x·y: 문구 덩어리 가운데 위치 (이미지 대비 0~1). scale: 글자 크기 배율 */
export interface TextState {
  text: string;
  style: string;
  x: number;
  y: number;
  scale: number;
}

// 서버 text_layout.position의 세로 범위 가운데 (core POSITIONS)
export const POSITION_Y = { top: 0.205, middle: 0.5, bottom: 0.795 } as const;

export const loadFont = (s: TextStyle) => document.fonts.load(`40px "${s.font}"`);

/** 글자 뒤 배경 밝기 (0~255). auto·gold 색 고르기용 */
function brightness(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number): number {
  const x0 = Math.max(0, Math.round(x)), y0 = Math.max(0, Math.round(y));
  const w0 = Math.max(1, Math.min(ctx.canvas.width - x0, Math.round(w))), h0 = Math.max(1, Math.min(ctx.canvas.height - y0, Math.round(h)));
  const d = ctx.getImageData(x0, y0, w0, h0).data;
  let sum = 0, n = 0;
  for (let i = 0; i < d.length; i += 4 * 16) { // 16픽셀마다 하나만 봄
    sum += d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114;
    n++;
  }
  return n ? sum / n : 255;
}

/** 원본 이미지 + 문구를 canvas에 그림. 글꼴은 loadFont로 먼저 받아 둘 것 */
export function drawText(canvas: HTMLCanvasElement, bg: HTMLImageElement, s: TextState) {
  const st = TEXT_STYLES.find((t) => t.id === s.style) ?? TEXT_STYLES[0];
  const W = (canvas.width = bg.naturalWidth);
  const H = (canvas.height = bg.naturalHeight);
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bg, 0, 0);
  if (!s.text.trim()) return;

  const size = W * st.size * s.scale;
  ctx.font = `${size}px "${st.font}"`;
  ctx.letterSpacing = `${size * st.tracking}px`;
  const lines = wrap((t) => ctx.measureText(t).width, s.text, W * Math.min(0.9, st.maxWidth * s.scale));
  const widths = lines.map((l) => ctx.measureText(l).width);
  const lineH = size * 1.22;
  const blockW = Math.max(...widths);
  const blockH = lineH * lines.length;
  // 끌어도 문구 덩어리(+장식 여백)가 이미지 밖으로 나가지 않게
  const fit = (v: number, half: number, max: number) => Math.min(Math.max(v, half), Math.max(half, max - half));
  const cx = fit(s.x * W, blockW / 2 + size * 0.3, W), cy = fit(s.y * H, blockH / 2 + size * 0.45, H);

  const dark = brightness(ctx, cx - blockW / 2, cy - blockH / 2, blockW, blockH) < 150;
  const fill = st.fill === "auto" ? (dark ? "#fff" : "rgb(38,38,38)") : st.fill === "gold" ? (dark ? "rgb(236,214,160)" : "rgb(70,48,28)") : st.fill;
  const decoColor = st.decoColor === "same" ? fill : st.decoColor ?? fill;
  const shadowColor = (st.fill === "auto" || st.fill === "gold") && !dark ? "rgba(255,255,255,.6)" : st.shadow?.[0];

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate((-st.rotate * Math.PI) / 180); // PIL rotate는 반시계 방향이 +
  if (st.shear) ctx.transform(1, 0, -st.shear, 1, 0, 0);
  ctx.textBaseline = "middle";
  ctx.textAlign = st.align;
  ctx.lineJoin = "round";
  const left = -blockW / 2;
  const tx = st.align === "left" ? left : 0;
  const ly = (i: number) => -blockH / 2 + lineH * (i + 0.5);

  if (st.back) {
    const [kind, color] = st.back;
    ctx.fillStyle = color;
    const pad = size * 0.45;
    if (kind === "band") ctx.fillRect(-cx, -blockH / 2 - pad, W, blockH + pad * 2);
    if (kind === "box") {
      ctx.beginPath();
      ctx.roundRect(left - pad, -blockH / 2 - pad * 0.6, blockW + pad * 2, blockH + pad * 1.2, size * 0.25);
      if (st.shadow) Object.assign(ctx, { shadowColor, shadowBlur: size * st.shadow[1], shadowOffsetY: size * st.shadow[2] });
      ctx.fill();
      ctx.shadowColor = "transparent";
    }
    if (kind === "highlight")
      lines.forEach((_, i) => {
        const lx = st.align === "left" ? left : -widths[i] / 2;
        ctx.fillRect(lx - size * 0.12, ly(i) - size * 0.05, widths[i] + size * 0.24, size * 0.55);
      });
  }

  const each = (fn: (line: string, y: number) => void) => lines.forEach((l, i) => fn(l, ly(i)));
  const strokeW = st.stroke ? Math.max(2, size * st.stroke[1]) : 0;

  // 흐린 그림자는 맨 아래 층에만 (box는 위에서 이미 씀)
  if (st.shadow && st.back?.[0] !== "box") Object.assign(ctx, { shadowColor, shadowBlur: size * st.shadow[1], shadowOffsetY: size * st.shadow[2] });
  if (st.depth) {
    const [color, dx, dy] = st.depth;
    ctx.fillStyle = ctx.strokeStyle = color;
    ctx.lineWidth = strokeW * 2;
    each((l, y) => {
      ctx.strokeText(l, tx + size * dx, y + size * dy);
      ctx.fillText(l, tx + size * dx, y + size * dy);
    });
    ctx.shadowColor = "transparent";
  }
  if (st.glow) Object.assign(ctx, { shadowColor: st.glow, shadowBlur: size * 0.35, shadowOffsetY: 0 });
  if (st.stroke) {
    ctx.strokeStyle = st.stroke[0];
    ctx.lineWidth = strokeW * 2;
    each((l, y) => ctx.strokeText(l, tx, y));
    if (!st.glow) ctx.shadowColor = "transparent";
  }
  if (fill !== "none") {
    ctx.fillStyle = fill;
    each((l, y) => ctx.fillText(l, tx, y));
    if (st.glow) each((l, y) => ctx.fillText(l, tx, y)); // 네온은 두 번 칠해 빛을 진하게
  }
  ctx.shadowColor = "transparent";

  ctx.strokeStyle = decoColor;
  ctx.fillStyle = decoColor;
  ctx.lineCap = "round";
  const top = -blockH / 2, bottom = blockH / 2;
  if (st.deco === "sparkle") {
    const firstW = widths[0];
    for (const side of [-1, 1]) {
      const sx = (st.align === "left" ? left + (side > 0 ? firstW : 0) : (side * firstW) / 2) + side * size * 0.2;
      for (const a of [-35, 0, 35]) {
        const r = (a * Math.PI) / 180;
        for (const [w, c] of [[size * 0.07 + 4, st.stroke?.[0] ?? decoColor], [size * 0.07, decoColor]] as const) {
          ctx.strokeStyle = c;
          ctx.lineWidth = w;
          ctx.beginPath();
          ctx.moveTo(sx + side * Math.cos(r) * size * 0.25, ly(0) + Math.sin(r) * size * 0.25);
          ctx.lineTo(sx + side * Math.cos(r) * size * 0.6, ly(0) + Math.sin(r) * size * 0.6);
          ctx.stroke();
        }
      }
    }
  } else if (st.deco === "wave") {
    const lastW = widths[widths.length - 1];
    const x0 = st.align === "left" ? left : -lastW / 2;
    for (const [w, c] of [[size * 0.1, st.stroke?.[0] ?? decoColor], [size * 0.06, decoColor]] as const) {
      ctx.strokeStyle = c;
      ctx.lineWidth = w;
      ctx.beginPath();
      for (let t = 0; t <= lastW; t += 4) ctx.lineTo(x0 + t, bottom + size * 0.1 + Math.sin((t / (size * 0.35)) * Math.PI) * size * 0.06);
      ctx.stroke();
    }
  } else if (st.deco === "rules") {
    const half = blockW * 0.42, r = size * 0.12;
    ctx.lineWidth = Math.max(2, size * 0.035);
    for (const yy of [top - size * 0.2, bottom + size * 0.2]) {
      ctx.beginPath();
      ctx.moveTo(-half, yy); ctx.lineTo(-size * 0.25, yy);
      ctx.moveTo(size * 0.25, yy); ctx.lineTo(half, yy);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, yy - r); ctx.lineTo(r, yy); ctx.lineTo(0, yy + r); ctx.lineTo(-r, yy);
      ctx.fill();
    }
  } else if (st.deco === "accent") {
    ctx.lineWidth = Math.max(3, size * 0.08);
    ctx.beginPath();
    ctx.moveTo(left, top - size * 0.3);
    ctx.lineTo(left + size * 1.3, top - size * 0.3);
    ctx.stroke();
  }
  ctx.restore();
}
