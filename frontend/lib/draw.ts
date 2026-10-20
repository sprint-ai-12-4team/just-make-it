// 글자 없는 이미지 위에 문구를 얹어 <canvas>에 그림. 미리보기와 다운로드가 같은 코드를 씀
export type Pos = "top" | "middle" | "bottom";
export interface Layout {
  pos: Pos;
  big: boolean;
}
export interface Panel {
  img: HTMLImageElement;
  title: string;
  sub?: string;
}

const FONT = "'Pretendard Variable', Pretendard, sans-serif";

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((ok, fail) => {
    const img = new Image();
    // 다운로드(toBlob)하려면 저장소에 CORS 허용 필요
    if (!src.startsWith("data:")) img.crossOrigin = "anonymous";
    img.onload = () => ok(img);
    img.onerror = fail;
    img.src = src;
  });
}

/** 한글은 글자 단위로도 줄바꿈. 공백이 있으면 공백에서 우선 끊음 */
export function wrap(measure: (s: string) => number, text: string, max: number): string[] {
  const lines: string[] = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const ch of para) {
      if (measure(line + ch) <= max || !line) {
        line += ch;
        continue;
      }
      const cut = line.lastIndexOf(" ");
      if (cut > 0 && ch !== " ") {
        lines.push(line.slice(0, cut));
        line = line.slice(cut + 1) + ch;
      } else {
        lines.push(line);
        line = ch === " " ? "" : ch;
      }
    }
    lines.push(line);
  }
  return lines;
}

function drawPanel(ctx: CanvasRenderingContext2D, p: Panel, top: number, w: number, h: number, layout: Layout) {
  ctx.drawImage(p.img, 0, top, w, h);
  const pad = w * 0.06;
  const titleSize = w * (layout.big ? 0.085 : 0.065);
  const subSize = titleSize * 0.5;
  const max = w - pad * 2;

  ctx.font = `700 ${titleSize}px ${FONT}`;
  const titleLines = wrap((s) => ctx.measureText(s).width, p.title, max);
  ctx.font = `500 ${subSize}px ${FONT}`;
  const subLines = p.sub ? wrap((s) => ctx.measureText(s).width, p.sub, max) : [];

  const blockH = titleLines.length * titleSize * 1.25 + (subLines.length ? subSize * 0.6 + subLines.length * subSize * 1.4 : 0);
  const bandH = blockH + pad * 2;
  const bandY = top + (layout.pos === "top" ? 0 : layout.pos === "middle" ? (h - bandH) / 2 : h - bandH);

  // 어떤 배경이든 글자가 읽히도록 반투명 먹색 띠
  ctx.fillStyle = "rgba(32, 32, 32, 0.62)";
  ctx.fillRect(0, bandY, w, bandH);
  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "top";
  let y = bandY + pad;
  ctx.font = `700 ${titleSize}px ${FONT}`;
  for (const l of titleLines) {
    ctx.fillText(l, pad, y);
    y += titleSize * 1.25;
  }
  y += subSize * 0.6;
  ctx.font = `500 ${subSize}px ${FONT}`;
  for (const l of subLines) {
    ctx.fillText(l, pad, y);
    y += subSize * 1.4;
  }
}

/** 패널 여러 개면 세로로 이어 붙임 (상세페이지 = 긴 이미지 한 장) */
export async function render(canvas: HTMLCanvasElement, panels: Panel[], layout: Layout, width: number) {
  await document.fonts.load(`700 40px ${FONT}`);
  const heights = panels.map((p) => (p.img.naturalHeight / p.img.naturalWidth) * width);
  canvas.width = width;
  canvas.height = heights.reduce((a, b) => a + b, 0);
  const ctx = canvas.getContext("2d")!;
  let top = 0;
  panels.forEach((p, i) => {
    drawPanel(ctx, p, top, width, heights[i], layout);
    top += heights[i];
  });
}

/** 저장소 CORS가 막혀 있으면 canvas가 오염돼 저장이 실패함 → 안내 문구로 알림 */
export function save(canvas: HTMLCanvasElement | null, name: string, onError: (msg: string) => void) {
  try {
    canvas!.toBlob((blob) => {
      if (!blob) return onError("저장하지 못했어요. 잠시 후 다시 시도해 주세요.");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }, "image/png");
  } catch {
    onError("저장하지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
}
