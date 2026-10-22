// ponytail: 서빙(API)이 생기기 전 화면 개발용 가짜 응답. NEXT_PUBLIC_MOCK=1일 때만 사용. 서빙 연결 후 파일째 삭제
import { SIZES, type DetailInput, type DetailPage, type GenerateInput, type Generation, type TextLayout } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const load = <T>(k: string): T | null => JSON.parse(sessionStorage.getItem(k) ?? "null");
const save = (k: string, v: unknown) => sessionStorage.setItem(k, JSON.stringify(v));

function fakeImage(w: number, h: number, hue = Math.floor(Math.random() * 360)): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="hsl(${hue},70%,75%)"/><stop offset="1" stop-color="hsl(${hue + 40},60%,45%)"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><circle cx="${w * 0.7}" cy="${h * 0.4}" r="${Math.min(w, h) * 0.22}" fill="white" opacity=".35"/></svg>`;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

/** 서버가 글자를 얹은 것처럼 SVG에 문구를 넣음. 글꼴은 이름만 흉내 (serif / sans) */
function fakeAd(g: Generation & { hue: number }): Generation {
  const { width: w, height: h, message, text_layout: t } = g;
  const y = { top: 0.2, middle: 0.5, bottom: 0.8 }[t!.position] * h;
  const family = t!.font === "batang" || t!.font === "yeonsung" ? "serif" : "sans-serif";
  const esc = message.replace(/[<&>]/g, (c) => `&#${c.charCodeAt(0)};`);
  const text = `<text x="50%" y="${y}" text-anchor="middle" dominant-baseline="middle" font-family="${family}" font-weight="700" font-size="${w * 0.08 * t!.size_scale}" fill="white" stroke="rgba(0,0,0,.5)" stroke-width="${w * 0.004}">${esc}</text>`;
  return { ...g, image_url: fakeImage(w, h, g.hue).replace(encodeURIComponent("</svg>"), encodeURIComponent(text + "</svg>")) };
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
    const hue = Math.floor(Math.random() * 360);
    const g = fakeAd({
      id: crypto.randomUUID(), status: "success", image_url: "", background_url: fakeImage(width, height, hue), hue,
      message, text_layout: { position: "top", font: "jua", size_scale: 1 }, source: "mock", width, height, parent_id, input,
    });
    save(`mock_g_${g.id}`, g);
    return g;
  },
  async editText(id: string, b: Partial<TextLayout> & { message?: string }) {
    await wait(300);
    const g = load<Generation & { hue: number }>(`mock_g_${id}`)!;
    const { message = g.message, ...layout } = b;
    const next = fakeAd({ ...g, message, text_layout: { ...g.text_layout!, ...layout } });
    save(`mock_g_${id}`, next);
    return next;
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
