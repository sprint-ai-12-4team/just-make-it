// ponytail: 서빙(API)이 생기기 전 화면 개발용 가짜 응답. NEXT_PUBLIC_MOCK=1일 때만 사용. 서빙 연결 후 파일째 삭제
import { SIZES, type DetailInput, type DetailPage, type GenerateInput, type Generation } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const load = <T>(k: string): T | null => JSON.parse(sessionStorage.getItem(k) ?? "null");
const save = (k: string, v: unknown) => sessionStorage.setItem(k, JSON.stringify(v));

function fakeImage(w: number, h: number, hue = Math.floor(Math.random() * 360)): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="hsl(${hue},70%,75%)"/><stop offset="1" stop-color="hsl(${hue + 40},60%,45%)"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><circle cx="${w * 0.7}" cy="${h * 0.4}" r="${Math.min(w, h) * 0.22}" fill="white" opacity=".35"/></svg>`;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

const ROLES = ["hero", "feature", "feature", "feature", "closing"] as const;

export const mock = {
  async suggestCopies(b: { product_name: string; message: string }) {
    await wait(800);
    return [`${b.product_name}, ${b.message}`, `지금 ${b.message}!`, `${b.message} — ${b.product_name}에서`];
  },
  async generate(b: GenerateInput): Promise<Generation> {
    await wait(1500);
    const [width, height] = SIZES[b.purpose];
    const message = b.adjustments.includes("텍스트 짧게") ? b.message.slice(0, 8) : b.message;
    const { parent_id, ...input } = b;
    const g: Generation = {
      id: crypto.randomUUID(), status: "success", image_url: fakeImage(width, height),
      message, source: "mock", width, height, parent_id, input,
    };
    save(`mock_g_${g.id}`, g);
    return g;
  },
  async getGeneration(id: string) {
    const g = load<Generation>(`mock_g_${id}`);
    if (!g) throw Object.assign(new Error("결과를 찾을 수 없어요."), { status: 404 });
    return g;
  },
  async startDetailPage(b: DetailInput) {
    const id = crypto.randomUUID();
    save(`mock_d_${id}`, { b, t: Date.now(), redo: {} });
    return id;
  },
  async getDetailPage(id: string): Promise<DetailPage> {
    const d = load<{ b: DetailInput; t: number; redo: Record<number, number> }>(`mock_d_${id}`);
    if (!d) throw Object.assign(new Error("결과를 찾을 수 없어요."), { status: 404 });
    const sections = ROLES.map((role, index) => {
      const started = d.redo[index] ?? d.t + index * 1500;
      const left = started + 1500 - Date.now();
      const title = index === 0 ? d.b.message : index === 4 ? `${d.b.product_name}, 지금 만나보세요` : d.b.features[index - 1] || `특징 ${index}`;
      return {
        index, role, title, body: `${d.b.product_name}의 ${title}을(를) 소개하는 두 줄 설명입니다.`,
        status: left > 1500 ? "pending" : left > 0 ? "processing" : "success",
        image_url: left > 0 ? null : fakeImage(1024, 1024, (index * 70 + started) % 360),
      } as DetailPage["sections"][number];
    });
    const done = sections.filter((s) => s.status === "success").length;
    return { id, status: done === 5 ? "success" : "processing", progress: { done, total: 5 }, sections };
  },
  async regenerateSection(id: string, index: number) {
    const d = load<{ redo: Record<number, number> }>(`mock_d_${id}`)!;
    d.redo[index] = Date.now();
    save(`mock_d_${id}`, d);
  },
};
