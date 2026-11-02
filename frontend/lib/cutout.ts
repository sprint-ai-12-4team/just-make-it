// 상품 사진 배경 지우기. 모델은 브라우저가 Hugging Face에서 직접 받음 → Vercel 대역폭 안 씀, 두 번째부터 브라우저 캐시
// BiRefNet_lite 512: MIT 라이선스(상업 사용 가능), fp16 약 99MB. revision 고정 → 저장소가 바뀌어도 결과 동일
// 1024 해상도판(onnx-community/BiRefNet_lite-ONNX)은 WASM 메모리 4GB를 넘겨 bad_alloc
const MODEL = "studioludens/birefnet-lite-512";
const REVISION = "962e67969ec6acec9c19fab76acee4f5e22e990c";

/** 배경 채우기 추천 색. 이 밖의 색은 색 고르기(input type=color)로 */
export const FILLS = [
  { name: "흰색", color: "#ffffff" },
  { name: "아이보리", color: "#fffaf0" },
  { name: "연회색", color: "#f3f3f3" },
  { name: "회색", color: "#bdbdbd" },
  { name: "먹색", color: "#202020" },
  { name: "베이지", color: "#eadcc4" },
  { name: "살구", color: "#ffd8b8" },
  { name: "연노랑", color: "#fff386" },
  { name: "노랑", color: "#ffdb5b" },
  { name: "주황", color: "#ff9f45" },
  { name: "코랄", color: "#ff8a7a" },
  { name: "빨강", color: "#e8343a" },
  { name: "연분홍", color: "#ffd6e0" },
  { name: "분홍", color: "#f78fb3" },
  { name: "라벤더", color: "#d9ccff" },
  { name: "보라", color: "#7b5cd6" },
  { name: "하늘", color: "#cfe8ff" },
  { name: "파랑", color: "#2f6fe4" },
  { name: "민트", color: "#c8f2e0" },
  { name: "초록", color: "#2fa86b" },
] as const;

export type Progress = (percent: number) => void;

type Remover = (image: HTMLCanvasElement) => Promise<{ toCanvas(): OffscreenCanvas | HTMLCanvasElement }>;
let remover: Promise<Remover> | null = null;

/** 모델 준비. 한 번 받은 파이프라인은 페이지를 떠날 때까지 재사용 */
function loadRemover(onProgress: Progress): Promise<Remover> {
  remover ??= (async () => {
    // 첫 화면 번들에 넣지 않도록 버튼을 누를 때 불러옴
    const { env, pipeline } = await import("@huggingface/transformers");
    // transformers.js 4.3.1은 revision 옵션을 일부 파일 요청에서 빠뜨림(main으로 받음) → 주소에 직접 고정
    env.remotePathTemplate = `{model}/resolve/${REVISION}/`;
    const progress_callback = (p: { status: string; progress?: number }) => {
      if (p.status === "progress" && p.progress != null) onProgress(Math.round(p.progress));
    };
    // ponytail: WASM(CPU)만 씀. WebGPU는 이 모델에서 GPU 한도 오류가 나고(셰이더 버퍼 11 > 10) 실패 후 WASM으로도 못 돌아옴.
    // onnxruntime-web이 고쳐지면 device "webgpu"로 바꿔 속도 확인
    const pipe = await pipeline("background-removal", MODEL, { revision: REVISION, dtype: "fp16", device: "wasm", progress_callback });
    return pipe as unknown as Remover;
  })().catch((e) => {
    remover = null; // 다음 시도에서 다시 받기
    throw e;
  });
  return remover;
}

// 같은 사진을 동시에 두 번 돌리면 메모리가 두 배 → 진행 중인 작업을 나눠 씀 (개발 모드 이중 실행, 연타)
let running: { src: string; mask: Promise<Uint8ClampedArray> } | null = null;

/** 사진의 각 픽셀이 상품인지(255) 배경인지(0) 나타내는 마스크 */
export function removeBackground(img: HTMLImageElement, onProgress: Progress): Promise<Uint8ClampedArray> {
  if (running?.src !== img.src) {
    const mask = maskOf(img, onProgress).finally(() => running?.mask === mask && (running = null));
    running = { src: img.src, mask };
  }
  return running.mask;
}

async function maskOf(img: HTMLImageElement, onProgress: Progress): Promise<Uint8ClampedArray> {
  // 이미 불러온 그림을 canvas로 넘김 → 다시 받지 않고, SVG 등 모델이 직접 못 읽는 형식도 처리
  const src = canvasOf(img.naturalWidth, img.naturalHeight);
  src.getContext("2d")!.drawImage(img, 0, 0);
  const out = (await (await loadRemover(onProgress))(src)).toCanvas();
  // 결과 크기가 원본과 달라도 원본 크기로 맞춰서 알파만 꺼냄
  const c = canvasOf(img.naturalWidth, img.naturalHeight);
  c.getContext("2d")!.drawImage(out, 0, 0, c.width, c.height);
  const rgba = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
  const alpha = new Uint8ClampedArray(c.width * c.height);
  for (let i = 0; i < alpha.length; i++) alpha[i] = rgba[i * 4 + 3];
  return alpha;
}

/**
 * Magic Wand: (x, y)와 색이 비슷하고 이어진 영역의 마스크를 value로 바꿈 (0 지우기, 255 되살리기)
 * 원본 색으로 영역을 찾으므로 이미 지운 곳에서도 동작. 상하좌우 4방향, 재귀 없이 스택으로
 */
export function floodFill(
  rgba: ArrayLike<number>,
  alpha: Uint8ClampedArray,
  width: number,
  height: number,
  x: number,
  y: number,
  value: number,
  tolerance = 48,
  sample = 0,
): Uint8ClampedArray {
  const next = alpha.slice();
  const seed = y * width + x;
  // 기준 색: 누른 곳 주변 (2·sample+1)² 칸 평균 (포토샵 "5x5 평균"). 잡티 한 점을 눌러도 영역이 좁아지지 않음
  let r0 = 0, g0 = 0, b0 = 0, n = 0;
  for (let dy = -sample; dy <= sample; dy++)
    for (let dx = -sample; dx <= sample; dx++) {
      const sx = x + dx, sy = y + dy;
      if (sx < 0 || sy < 0 || sx >= width || sy >= height) continue;
      const q = (sy * width + sx) * 4;
      r0 += rgba[q]; g0 += rgba[q + 1]; b0 += rgba[q + 2]; n++;
    }
  r0 /= n; g0 /= n; b0 /= n;
  const near = (p: number) =>
    Math.max(Math.abs(rgba[p * 4] - r0), Math.abs(rgba[p * 4 + 1] - g0), Math.abs(rgba[p * 4 + 2] - b0)) <= tolerance;
  const seen = new Uint8Array(width * height);
  const stack = [seed];
  seen[seed] = 1;
  while (stack.length) {
    const p = stack.pop()!;
    next[p] = value;
    const px = p % width;
    for (const q of [px > 0 ? p - 1 : -1, px < width - 1 ? p + 1 : -1, p - width, p + width]) {
      if (q < 0 || q >= seen.length || seen[q] || !near(q)) continue;
      seen[q] = 1;
      stack.push(q);
    }
  }
  return next;
}

/** 상품 자리: 가운데에서 옮긴 거리(이미지 대비), 크기, 회전(도), 기울기(도), 뒤집기 */
export interface Place {
  x: number;
  y: number;
  scale: number;
  rotate: number;
  skew: number;
  flipX: boolean;
  flipY: boolean;
}
export const HOME: Place = { x: 0, y: 0, scale: 1, rotate: 0, skew: 0, flipX: false, flipY: false };

/** 상품 층 좌표 → 그림 좌표. 역행렬로 누른 곳이 원본 사진의 어느 픽셀인지도 찾음 */
export function placeMatrix(w: number, h: number, p: Place): DOMMatrix {
  return new DOMMatrix()
    .translate(w / 2 + p.x * w, h / 2 + p.y * h)
    .rotate(p.rotate)
    .skewX(p.skew)
    .scale(p.scale * (p.flipX ? -1 : 1), p.scale * (p.flipY ? -1 : 1))
    .translate(-w / 2, -h / 2);
}

/** 원본 + 마스크 → 배경이 투명한 상품 층. 마스크가 바뀔 때만 다시 만듦 (옮길 때마다 만들면 느림) */
export function cutOf(img: HTMLImageElement, alpha: Uint8ClampedArray): HTMLCanvasElement {
  const cut = canvasOf(img.naturalWidth, img.naturalHeight);
  const cx = cut.getContext("2d")!;
  cx.drawImage(img, 0, 0);
  const data = cx.getImageData(0, 0, cut.width, cut.height);
  for (let i = 0; i < alpha.length; i++) data.data[i * 4 + 3] = alpha[i];
  cx.putImageData(data, 0, 0);
  return cut;
}

/** 배경색 + 상품 층을 canvas에 그림 (미리보기·저장 공용). 크기는 원본 사진 그대로. fill이 ""면 투명 */
export function compose(canvas: HTMLCanvasElement, cut: HTMLCanvasElement, fill: string, place: Place) {
  const { width: w, height: h } = cut;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  if (fill) {
    // 빈 값이면 투명 그대로 (배경은 AI 장면으로, api_spec_next 4장)
    ctx.fillStyle = fill;
    ctx.fillRect(0, 0, w, h);
  }
  ctx.setTransform(placeMatrix(w, h, place));
  ctx.drawImage(cut, 0, 0);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

/** 원본 픽셀 (Magic Wand가 색을 비교할 때 씀) */
export function pixelsOf(img: HTMLImageElement): Uint8ClampedArray {
  const c = canvasOf(img.naturalWidth, img.naturalHeight);
  c.getContext("2d")!.drawImage(img, 0, 0);
  return c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
}

export function canvasOf(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

/** 투명하지 않은 부분의 사각형 (상품만 잘라 쓰려고). 다 투명하면 null */
export function alphaBox(alpha: ArrayLike<number>, w: number, h: number) {
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      if (alpha[y * w + x] > 8) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        y1 = y;
      }
  return x1 < 0 ? null : { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
}

/** 장면 가운데 아래에 상품을 놓을 자리: 가로 60%·세로 55% 안, 바닥은 높이의 92% (api_spec_next 4장의 비운 구도) */
export function fitBottom(pw: number, ph: number, W: number, H: number) {
  const s = Math.min((W * 0.6) / pw, (H * 0.55) / ph);
  const w = pw * s, h = ph * s;
  return { x: (W - w) / 2, y: H * 0.92 - h, w, h };
}

/** AI 장면 + 사용자 상품(픽셀 그대로) + 바닥 그림자 → 글자 없는 그림 */
export function placeOnScene(scene: HTMLImageElement, product: HTMLImageElement): HTMLCanvasElement {
  const W = scene.naturalWidth, H = scene.naturalHeight;
  const out = canvasOf(W, H);
  const ctx = out.getContext("2d")!;
  ctx.drawImage(scene, 0, 0);
  const rgba = pixelsOf(product);
  const pw = product.naturalWidth, ph = product.naturalHeight;
  const box = alphaBox(rgba.filter((_, i) => i % 4 === 3), pw, ph) ?? { x: 0, y: 0, w: pw, h: ph };
  const r = fitBottom(box.w, box.h, W, H);
  // 그림자: 흐린 타원 (ctx.filter 없이 그라디언트라 사파리에서도 같음)
  const cx = W / 2, cy = r.y + r.h, rx = r.w * 0.45, ry = Math.max(4, r.h * 0.06);
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, ry / rx);
  const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rx);
  g.addColorStop(0, "rgba(0,0,0,0.35)");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(-rx, -rx, rx * 2, rx * 2);
  ctx.restore();
  ctx.drawImage(product, box.x, box.y, box.w, box.h, r.x, r.y, r.w, r.h);
  return out;
}
