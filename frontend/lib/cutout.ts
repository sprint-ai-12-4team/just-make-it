// 상품 사진 배경 지우기. 모델은 브라우저가 Hugging Face에서 직접 받음 → Vercel 대역폭 안 씀, 두 번째부터 브라우저 캐시
// BiRefNet_lite 512: MIT 라이선스(상업 사용 가능), fp16 약 99MB. revision 고정 → 저장소가 바뀌어도 결과 동일
// 1024 해상도판(onnx-community/BiRefNet_lite-ONNX)은 WASM 메모리 4GB를 넘겨 bad_alloc
const MODEL = "studioludens/birefnet-lite-512";
const REVISION = "962e67969ec6acec9c19fab76acee4f5e22e990c";

/** 배경 채우기 색 (DESIGN.md 팔레트 안에서만) */
export const FILLS = [
  { id: "white", name: "흰색", color: "#ffffff" },
  { id: "mist", name: "연회색", color: "#f3f3f3" },
  { id: "pollen", name: "연노랑", color: "#fff386" },
  { id: "honey", name: "노랑", color: "#ffdb5b" },
] as const;

export type Progress = (percent: number) => void;

type Remover = (src: string) => Promise<{ toCanvas(): OffscreenCanvas | HTMLCanvasElement }>;
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
  const out = (await (await loadRemover(onProgress))(img.src)).toCanvas();
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
  tolerance = 32,
): Uint8ClampedArray {
  const next = alpha.slice();
  const seed = y * width + x;
  const [r0, g0, b0] = [rgba[seed * 4], rgba[seed * 4 + 1], rgba[seed * 4 + 2]];
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

/** 원본 + 마스크 + 배경색을 canvas에 그림 (미리보기·저장 공용) */
export function compose(canvas: HTMLCanvasElement, img: HTMLImageElement, alpha: Uint8ClampedArray, fill: string) {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const cut = canvasOf(w, h);
  const cx = cut.getContext("2d")!;
  cx.drawImage(img, 0, 0);
  const data = cx.getImageData(0, 0, w, h);
  for (let i = 0; i < alpha.length; i++) data.data[i * 4 + 3] = alpha[i];
  cx.putImageData(data, 0, 0);

  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(cut, 0, 0);
}

/** 원본 픽셀 (Magic Wand가 색을 비교할 때 씀) */
export function pixelsOf(img: HTMLImageElement): Uint8ClampedArray {
  const c = canvasOf(img.naturalWidth, img.naturalHeight);
  c.getContext("2d")!.drawImage(img, 0, 0);
  return c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
}

function canvasOf(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}
