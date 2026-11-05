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

/** 단어별로 나눠 고칠 때 한 단어. 비어 있는 값은 전체 설정(TextState)을 따름 */
export interface WordState {
  text: string;
  x: number; // 단어 가운데 (이미지 대비 0~1)
  y: number;
  size: number; // 나누던 순간의 글자 크기 (이미지 가로 대비, 전체 배율 1 기준)
  scale?: number; // 이 단어만 키우기·줄이기
  style?: string;
  font?: string;
  color?: string;
}

/** x·y: 문구 덩어리 가운데 위치 (이미지 대비 0~1). scale: 글자 크기 배율. font·color: 스타일 대신 쓸 글꼴·색
 *  words가 있으면 단어마다 따로 그림 (scale·style·font·color는 전체에 한꺼번에 적용) */
export interface TextState {
  text: string;
  style: string;
  x: number;
  y: number;
  scale: number;
  font?: string;
  color?: string;
  words?: WordState[];
}

/** 화면 표시·끌기용 글자 영역 (이미지 대비 0~1) */
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

// 서버 text_layout.position의 세로 범위 가운데 (core POSITIONS)
export const POSITION_Y = { top: 0.205, middle: 0.5, bottom: 0.795 } as const;

// 글꼴만 바꾸기용 (globals.css @font-face 이름)
export const FONTS = [
  { id: "Jua", name: "주아" },
  { id: "YeonSung", name: "연성" },
  { id: "GowunBatang", name: "고운바탕" },
  { id: "GowunDodum", name: "고운돋움" },
  { id: "BlackHanSans", name: "검은고딕" },
];

const styleOf = (id?: string) => TEXT_STYLES.find((t) => t.id === id) ?? TEXT_STYLES[0];

/** 그릴 때 쓰는 글꼴을 모두 받아 둠 (단어별 글꼴 포함). 실패해도 기본 글꼴로 그림 */
export function loadFonts(s: TextState) {
  const fonts = new Set([s.font ?? styleOf(s.style).font]);
  for (const w of s.words ?? []) fonts.add(w.font ?? s.font ?? styleOf(w.style ?? s.style).font);
  return Promise.all([...fonts].map((f) => document.fonts.load(`40px "${f}"`))).catch(() => {});
}

/** 단어 → 문구 (단어별 편집 중에도 text를 맞춰 둬 다시 만들기·저장·문구 키트가 그대로 동작) */
export const joinWords = (words: WordState[]) => words.map((w) => w.text.trim()).filter(Boolean).join(" ");

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

// 서버 POSITIONS 한 칸의 높이 (이미지 대비). 서버는 문구가 이 높이의 85%를 넘으면 글자를 줄임
const AREA_H = 0.35;

const setFont = (ctx: CanvasRenderingContext2D, st: TextStyle, font: string, size: number) => {
  ctx.font = `${size}px "${font}"`;
  ctx.letterSpacing = `${size * st.tracking}px`;
};

/** 한 덩어리 문구의 줄·크기·가운데 (core design_text와 같은 규칙) */
function layoutBlock(ctx: CanvasRenderingContext2D, s: TextState, W: number, H: number) {
  const st = styleOf(s.style);
  const font = s.font ?? st.font;
  // 정해진 너비·높이에 들어갈 때까지 2px씩 줄임 → 서버가 얹은 줄 수·크기와 맞춤
  // 크기를 키우면(scale > 1) 높이 한도도 같이 늘려서 슬라이더가 먹히게 함
  const maxW = W * Math.min(0.9, st.maxWidth * s.scale);
  const maxH = H * AREA_H * 0.85 * Math.max(1, s.scale);
  let size = Math.floor(W * st.size * s.scale);
  let lines: string[] = [], widths: number[] = [];
  for (;;) {
    setFont(ctx, st, font, size);
    lines = wrap((t) => ctx.measureText(t).width, s.text, maxW);
    widths = lines.map((l) => ctx.measureText(l).width);
    if ((Math.max(...widths) <= maxW && size * 1.22 * lines.length <= maxH) || size <= W * 0.04) break;
    size -= 2;
  }
  const lineH = size * 1.22;
  const blockW = Math.max(...widths);
  const blockH = lineH * lines.length;
  // 끌어도 문구 덩어리(+장식 여백)가 이미지 밖으로 나가지 않게
  const fit = (v: number, half: number, max: number) => Math.min(Math.max(v, half), Math.max(half, max - half));
  const cx = fit(s.x * W, blockW / 2 + size * 0.3, W), cy = fit(s.y * H, blockH / 2 + size * 0.45, H);
  return { st, font, size, lines, widths, lineH, blockW, blockH, cx, cy };
}

interface Piece {
  st: TextStyle;
  font: string;
  color?: string;
  size: number;
  lines: string[];
  widths: number[];
  cx: number;
  cy: number;
  deco: boolean;
}

/** 줄 묶음 하나를 (cx, cy) 가운데에 스타일 효과와 함께 그림. 그린 영역(px)을 돌려줌 */
function drawPiece(ctx: CanvasRenderingContext2D, W: number, p: Piece) {
  const { st, size, lines, widths, cx, cy } = p;
  setFont(ctx, st, p.font, size);
  const lineH = size * 1.22;
  const blockW = Math.max(...widths);
  const blockH = lineH * lines.length;
  const box = { x: cx - blockW / 2 - size * 0.3, y: cy - blockH / 2 - size * 0.3, w: blockW + size * 0.6, h: blockH + size * 0.6 };

  const dark = brightness(ctx, cx - blockW / 2, cy - blockH / 2, blockW, blockH) < 150;
  const auto = !p.color && (st.fill === "auto" || st.fill === "gold");
  const fill = p.color ?? (st.fill === "auto" ? (dark ? "#fff" : "rgb(38,38,38)") : st.fill === "gold" ? (dark ? "rgb(236,214,160)" : "rgb(70,48,28)") : st.fill);
  const decoColor = st.decoColor === "same" || p.color ? fill : st.decoColor ?? fill;
  const shadowColor = auto && !dark ? "rgba(255,255,255,.6)" : st.shadow?.[0];

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
    // 단어마다 가로 전체 띠를 깔면 겹쳐서 진해짐 → 단어별일 때는 상자로
    const [kind, color] = st.back[0] === "band" && !p.deco ? (["box", st.back[1]] as const) : st.back;
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

  // ponytail: 장식(반짝이·물결 등)은 문구 덩어리에만. 단어마다 붙이면 지저분해서 뺌
  if (p.deco) drawDeco(ctx, st, size, widths, blockW, blockH, left, ly, decoColor);
  ctx.restore();
  return box;
}

function drawDeco(ctx: CanvasRenderingContext2D, st: TextStyle, size: number, widths: number[], blockW: number, blockH: number, left: number, ly: (i: number) => number, decoColor: string) {
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
}

/** 원본 이미지(또는 canvas) + 문구를 canvas에 그림. 글꼴은 loadFonts로 먼저 받아 둘 것.
 *  돌려주는 값: 글자 영역들 (단어별이면 단어 순서대로, 아니면 덩어리 하나) */
export function drawText(canvas: HTMLCanvasElement, bg: HTMLImageElement | HTMLCanvasElement, s: TextState): Box[] {
  const W = (canvas.width = bg instanceof HTMLImageElement ? bg.naturalWidth : bg.width);
  const H = (canvas.height = bg instanceof HTMLImageElement ? bg.naturalHeight : bg.height);
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bg, 0, 0);
  const rel = (b: { x: number; y: number; w: number; h: number }): Box => ({ x: b.x / W, y: b.y / H, w: b.w / W, h: b.h / H });

  if (s.words) {
    return s.words.map((w) => {
      const st = styleOf(w.style ?? s.style);
      const font = w.font ?? s.font ?? st.font;
      const size = Math.max(4, W * w.size * (w.scale ?? 1) * s.scale);
      setFont(ctx, st, font, size);
      const text = w.text.trim();
      if (!text) return { x: w.x, y: w.y, w: 0, h: 0 };
      return rel(drawPiece(ctx, W, { st, font, color: w.color ?? s.color, size, lines: [text], widths: [ctx.measureText(text).width], cx: w.x * W, cy: w.y * H, deco: false }));
    });
  }
  if (!s.text.trim()) return [];
  const l = layoutBlock(ctx, s, W, H);
  return [rel(drawPiece(ctx, W, { ...l, color: s.color, deco: true }))];
}

/** 한 덩어리 문구를 지금 보이는 자리 그대로 단어로 나눔. 줄이 바뀌는 곳도 단어 경계로 봄 */
export function splitWords(W: number, H: number, s: TextState): TextState {
  const ctx = document.createElement("canvas").getContext("2d")!;
  const l = layoutBlock(ctx, s, W, H);
  const rad = (-l.st.rotate * Math.PI) / 180;
  const words: WordState[] = [];
  l.lines.forEach((line, i) => {
    const left = l.st.align === "left" ? -l.blockW / 2 : -l.widths[i] / 2;
    const y = -l.blockH / 2 + l.lineH * (i + 0.5);
    let at = 0;
    for (const part of line.split(" ")) {
      const start = ctx.measureText(line.slice(0, at)).width;
      at += part.length + 1;
      if (!part) continue;
      // 덩어리를 기울이고 돌린 것과 같게 단어 가운데를 옮김 (그리기: 회전 → 기울이기 순)
      const x0 = left + start + ctx.measureText(part).width / 2;
      const xs = x0 - l.st.shear * y;
      words.push({
        text: part,
        x: (l.cx + xs * Math.cos(rad) - y * Math.sin(rad)) / W,
        y: (l.cy + xs * Math.sin(rad) + y * Math.cos(rad)) / H,
        size: l.size / W / s.scale,
      });
    }
  });
  return { ...s, words };
}

/** 추천받은 문구를 결과 화면에서 다시 고를 수 있게 이 브라우저 탭에만 보관 (생성 id별) */
const copiesKey = (id: string) => `jmi_copies_${id}`;

export function saveCopies(id: string, copies: string[]) {
  if (!copies.length) return;
  try {
    sessionStorage.setItem(copiesKey(id), JSON.stringify(copies));
  } catch {}
}

export function loadCopies(id: string): string[] {
  try {
    return JSON.parse(sessionStorage.getItem(copiesKey(id)) ?? "[]");
  } catch {
    return [];
  }
}
