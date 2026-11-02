// ponytail: 서빙(API)이 생기기 전 화면 개발용 가짜 응답. NEXT_PUBLIC_MOCK=1일 때만 사용. 서빙 연결 후 파일째 삭제
import { SIZES, type Brief, type Consult, type ConsultTurn, type ConvertFormat, type ConvertResult, type DetailInput, type DetailPage, type EventType, type FamilyItem, type GenerateInput, type Generation, type Purpose } from "./types";

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

const dataUrl = (blob: Blob) =>
  new Promise<string>((ok) => {
    const r = new FileReader();
    r.onload = () => ok(r.result as string);
    r.readAsDataURL(blob);
  });

const ROLES = ["hero", "feature", "feature", "feature", "closing"] as const;

// 상담 대본 = 섞기안: 고정 질문 + 칩 (모델 없음). 실제 서버는 직접 쓴 답만 luna가 정리, 기획서는 terra 1회
// 순서: 업종 → 목표 → (상품 이름) → 주 고객 → 강점 → 기간 → 채널
const ASK: [string, string[]][] = [
  ["안녕하세요 사장님! 이번 광고 같이 만들어 볼게요. 어떤 가게를 하고 계세요?", ["카페", "음식점", "미용", "꽃집", "옷가게"]],
  ["좋아요. 이번에 제일 알리고 싶은 건 뭐예요?", ["신메뉴", "할인", "새로 열었어요", "단골 감사"]],
  ["알리고 싶은 상품이나 메뉴 이름을 적어 주세요.", []],
  ["주로 어떤 손님이 오세요?", ["동네 주민", "직장인", "학생", "가족", "관광객"]],
  ["손님들이 우리 가게에서 제일 좋아하는 건 뭐예요?", ["맛", "가격", "분위기", "친절", "양", "모르겠어요"]],
  ["언제까지 하는 행사예요?", ["이번 주말까지", "이번 달까지", "기간 없어요"]],
  ["어디에 올리고 싶으세요?", ["인스타그램", "네이버 플레이스", "카카오톡 채널", "스마트스토어 · 쿠팡", "잘 모르겠어요"]],
];
const CHANNEL: Record<string, [Purpose, string, string]> = {
  "인스타그램": ["instagram", "인스타그램", "사진으로 보여 주기 좋은 메뉴라서요."],
  "네이버 플레이스": ["free", "네이버 플레이스", "가게를 찾아보는 손님이 먼저 보는 곳이에요."],
  "카카오톡 채널": ["kakao", "카카오톡 채널", "이미 친구인 단골에게 바로 닿아요."],
  "스마트스토어 · 쿠팡": ["commerce", "스마트스토어 · 쿠팡", "바로 살 수 있는 곳에 올리면 좋아요."],
};
const OFF_TOPIC = /숙제|코딩|주식|코인|대출|세금|시스템 프롬프트/;
const MAX_OFF = 3; // 같은 상담에서 3번 연속 주제 밖이면 종료 (제안서 안전장치)
type MockConsult = Consult & { answers: string[]; off: number; start: { purpose?: Purpose; product_name?: string } };

function makeBrief(c: MockConsult, tweak?: string): Brief {
  const a = c.answers;
  const [purpose, channel, why] = CHANNEL[a[6]] ?? [c.start.purpose ?? "instagram", "인스타그램", "처음 시작하기 가장 쉬운 곳이에요."];
  const p = a[2];
  const strengths = a[4] === "모르겠어요" ? [] : [a[4]];
  return {
    category: a[0], goal: a[1], product_name: p, period: a[5] === "기간 없어요" ? null : a[5], strengths, audience: a[3],
    purpose, channel, message: `${a[3]}이 먼저 찾는 ${p}`,
    copies: tweak ? [tweak, `${a[1]}! ${p}`] : [`${a[1]}! ${p}`, `${strengths[0] ?? "정성"} 가득 ${p}`],
    style: "따뜻한", reason: `${why} ${a[3]} 손님이 좋아하는 ‘${strengths[0] ?? p}’을 앞에 두었어요.`,
    next_tips: purpose === "kakao" ? ["광고 메시지는 맨 앞에 '(광고)'를 넣어 주세요."] : [],
  };
}

function consultTurn(c: MockConsult, offTopic = false): ConsultTurn {
  const n = c.answers.length;
  let reply: string;
  let chips: string[] = [];
  if (offTopic && c.off >= MAX_OFF) {
    c.ended = true;
    reply = "광고 이야기가 아니라서 상담을 여기서 마칠게요. 바로 만들기는 언제든 쓸 수 있어요.";
  } else if (offTopic) {
    const last = [...c.messages].reverse().find((m) => m.role === "assistant")!;
    reply = "그 부분은 제가 도와드리기 어려워요. 대신 이번 광고 이야기를 이어 갈게요. " + last.text;
    chips = last.chips ?? [];
  } else if (c.brief) {
    // 기획서 고치기: 남은 횟수만큼 (terra 1~2회)
    c.edits_left = (c.edits_left ?? 2) - 1;
    c.brief = makeBrief(c, c.messages.at(-1)?.text);
    reply = "고쳐서 다시 정리했어요.";
  } else if (n < ASK.length) {
    [reply, chips] = ASK[n];
    if (n === 2 && c.start.product_name) chips = [c.start.product_name];
  } else {
    c.brief = makeBrief(c);
    c.edits_left = 2;
    reply = "정리했어요! 아래 내용으로 바로 만들 수 있어요. 바꾸고 싶은 게 있으면 적어 주세요.";
  }
  if (c.edits_left === 0) c.ended = true;
  c.messages.push({ role: "assistant", text: reply, chips });
  save(`mock_c_${c.id}`, c);
  return { id: c.id, reply, chips, allow_free_text: !c.ended, turn: n + 1, max_turns: 12, brief: c.brief, ended: c.ended, edits_left: c.edits_left };
}

const CONVERT: Record<ConvertFormat, (t: string, p: string) => ConvertResult> = {
  instagram_post: (t, p) => `${t} ✨\n\n오늘도 ${p} 준비했어요.\n가까이 계시면 들러 주세요!`,
  instagram_hashtags: (_, p) => [`#${p}`, "#동네맛집", "#오늘의메뉴", "#신메뉴", "#소상공인", "#동네가게", "#데일리", "#추천", "#방문환영", "#단골환영"],
  instagram_location: () => ["망원동", "망원역 근처", "마포구"],
  instagram_story: (t) => t.slice(0, 15),
  naver_coupon: (t) => ({ title: t, condition: "(조건을 적어 주세요)", period: "(기간을 적어 주세요)" }),
  naver_blog_title: (t, p) => [`${p}, ${t}`, `요즘 ${p} 찾는다면`, `${t} — 직접 만든 ${p} 이야기`],
  store_description: (t, p) => `${p}\n\n${t}\n매일 정성껏 준비합니다. 궁금한 점은 언제든 물어봐 주세요.`,
};

export const mock = {
  async suggestCopies(b: { product_name: string; message: string }) {
    await wait(800);
    return [`${b.product_name}, ${b.message}`, `지금 ${b.message}!`, `${b.message} — ${b.product_name}에서`];
  },
  async generate(b: GenerateInput, file?: File | null, delay = 1500): Promise<Generation> {
    await wait(delay);
    const [width, height] = SIZES[b.purpose];
    const message = b.adjustments.includes("텍스트 짧게") ? b.message.slice(0, 8) : b.message;
    const { parent_id, ...input } = b;
    const hue = Math.floor(Math.random() * 360);
    const g = fakeAd({
      id: crypto.randomUUID(), status: "success", image_url: "", background_url: fakeImage(width, height, hue), hue,
      message, text_layout: { position: "top", font: "jua", size_scale: 1 }, source: "mock", width, height, parent_id, input,
      created_at: new Date().toISOString(),
    });
    // keep_product: 서버는 상품 없는 장면만 그리고 받은 투명 사진을 product_url로 돌려줌. 다시 만들 때는 부모 것 재사용
    if (b.keep_product) {
      g.product_url = file ? await dataUrl(file) : parent_id ? (load<Generation>(`mock_g_${parent_id}`)?.product_url ?? null) : null;
      g.image_url = g.background_url!; // 서버도 장면에 글자를 얹지만, 프론트가 바로 합쳐 덮어씀
    }
    save(`mock_g_${g.id}`, g);
    return g;
  },
  /** 바로 id를 주고 6초 동안 processing (앞 3초는 대기, 뒤 3초는 그리는 중) */
  async startGeneration(b: GenerateInput, file?: File | null) {
    const g = await mock.generate(b, file, 0);
    save(`mock_ready_${g.id}`, Date.now() + 6000);
    return g.id;
  },
  async getGeneration(id: string): Promise<Generation> {
    const g = load<Generation>(`mock_g_${id}`);
    if (!g) throw Object.assign(new Error("결과를 찾을 수 없어요."), { status: 404 });
    const left = (load<number>(`mock_ready_${id}`) ?? 0) - Date.now();
    if (left > 0)
      return { ...g, status: "processing", image_url: "", progress: { stage: left > 3000 ? "queued" : "running", jobs_ahead: left > 3000 ? 1 : 0, estimated_seconds: left / 1000 } };
    return g;
  },
  async logEvent(id: string, type: EventType, detail?: object) {
    console.info("[mock] event", id, type, detail ?? "");
    return null;
  },
  async saveImage(id: string, image: Blob, background?: Blob | null, message?: string): Promise<Generation> {
    await wait(500);
    const g = await mock.getGeneration(id);
    // data URL로 바꿔 sessionStorage에 저장 (새로고침해도 고친 그림이 보이게)
    const next = {
      ...g,
      image_url: await dataUrl(image),
      ...(background && { background_url: await dataUrl(background) }),
      edited: true,
      message: message || g.message,
    };
    save(`mock_g_${id}`, next);
    return next;
  },
  async getFamily(id: string): Promise<FamilyItem[]> {
    // 실제 서버와 같은 규칙: 맨 처음 결과를 찾고 그 아래 전부
    const all = Object.keys(sessionStorage).filter((k) => k.startsWith("mock_g_")).map((k) => load<Generation>(k)!);
    const byId = new Map(all.map((g) => [g.id, g]));
    if (!byId.has(id)) throw Object.assign(new Error("결과를 찾을 수 없어요."), { status: 404 });
    let root = id;
    while (byId.get(root)?.parent_id && byId.has(byId.get(root)!.parent_id!)) root = byId.get(root)!.parent_id!;
    const ids = new Set([root]);
    for (let grew = true; grew; ) {
      grew = false;
      for (const g of all) if (g.parent_id && ids.has(g.parent_id) && !ids.has(g.id)) (ids.add(g.id), (grew = true));
    }
    return all
      .filter((g) => ids.has(g.id))
      .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""))
      .map((g) => ({ id: g.id, parent_id: g.parent_id ?? null, image_url: g.image_url, created_at: g.created_at }));
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
  async getTips(): Promise<never> {
    throw Object.assign(new Error("없음"), { status: 404 }); // 서버 카드가 없을 때처럼 기본 카드를 씀
  },
  async startConsult(b: { purpose?: Purpose; product_name?: string }) {
    await wait(300);
    const c: MockConsult = { id: crypto.randomUUID(), messages: [], brief: null, answers: [], off: 0, start: b };
    return consultTurn(c);
  },
  async sendConsult(id: string, text: string) {
    await wait(900);
    const c = load<MockConsult>(`mock_c_${id}`);
    if (!c) throw Object.assign(new Error("상담을 찾을 수 없어요."), { status: 404 });
    c.messages.push({ role: "user", text });
    if (c.ended) throw Object.assign(new Error("상담이 끝났어요."), { status: 409 });
    const off = OFF_TOPIC.test(text);
    c.off = off ? c.off + 1 : 0;
    if (!off && !c.brief) c.answers.push(text);
    return consultTurn(c, off);
  },
  async getConsult(id: string): Promise<Consult> {
    const c = load<MockConsult>(`mock_c_${id}`);
    if (!c) throw Object.assign(new Error("상담을 찾을 수 없어요."), { status: 404 });
    return { id: c.id, messages: c.messages, brief: c.brief, ended: c.ended, edits_left: c.edits_left };
  },
  async convertCopy(b: { text: string; format: ConvertFormat; product_name?: string; area?: string; facts?: Record<string, string> }) {
    await wait(700);
    let result = CONVERT[b.format](b.text, b.product_name || "우리 가게");
    if (b.format === "instagram_location" && b.area) result = [b.area, `${b.area} 근처`, `${b.area} 맛집`];
    if (b.format === "naver_coupon" && b.facts)
      result = { title: `${b.facts.discount ?? ""} ${b.text}`.trim(), condition: b.facts.discount ? `${b.facts.discount} 할인` : "(조건을 적어 주세요)", period: b.facts.until ? b.facts.until.replace(/(까지)?$/, "까지") : "(기간을 적어 주세요)" };
    return { result, fixed_typos: false };
  },
  async regenerateSection(id: string, index: number) {
    const d = load<{ redo: Record<number, number> }>(`mock_d_${id}`)!;
    d.redo[index] = Date.now();
    save(`mock_d_${id}`, d);
  },
};
