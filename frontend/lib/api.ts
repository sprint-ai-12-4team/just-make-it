import { mock } from "./mock";
import type { DetailInput, DetailPage, EventType, FamilyItem, GenerateInput, Generation, TextModel } from "./types";

// next.config.ts의 rewrites로 NEXT_PUBLIC_API_URL에 프록시. https(Vercel) → http(VM) 혼합 콘텐츠·CORS 회피
const BASE = "/api/backend";
const USE_MOCK = process.env.NEXT_PUBLIC_MOCK === "1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** 브라우저별 익명 ID (api_spec 1장). 로그인 없음 */
function clientId(): string {
  let id = localStorage.getItem("jmi_client_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("jmi_client_id", id);
  }
  return id;
}

/** 사진이 있으면 multipart, 없으면 JSON. 배열은 같은 이름으로 여러 번 보냄 */
function toBody(data: object, file?: File | null): BodyInit {
  if (!file) return JSON.stringify(data);
  const form = new FormData();
  for (const [k, v] of Object.entries(data)) {
    if (v == null) continue;
    for (const item of Array.isArray(v) ? v : [v]) form.append(k, String(item));
  }
  form.append("reference_image", file);
  return form;
}

async function call<T>(path: string, init: { method?: string; body?: BodyInit } = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Client-Id": clientId() };
  // 204(본문 없음)는 아래 res.json()이 null로 처리
  if (typeof init.body === "string") headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new ApiError(0, "인터넷 연결을 확인하고 다시 시도해 주세요.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    // 422 등 서버 내부 형식은 사용자에게 보여주지 않음
    const msg = typeof data?.detail === "string" ? data.detail : "잠시 후 다시 시도해 주세요.";
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

/** 서버는 PUBLIC_BASE_URL(http://VM)로 이미지 주소를 줌 → 프록시 경로로 바꿔 혼합 콘텐츠·canvas CORS 회피 */
function viaProxy<T extends { image_url: string | null }>(x: T): T {
  if (!x.image_url) return x;
  const { pathname } = new URL(x.image_url, location.href);
  return pathname.startsWith("/images/") ? { ...x, image_url: BASE + pathname } : x;
}

const real = {
  suggestCopies: (b: { product_name: string; message: string; style: string | null; text_model: TextModel }) =>
    call<{ copies: string[] }>("/copies", { method: "POST", body: toBody(b) }).then((r) => r.copies),
  generate: (b: GenerateInput, file?: File | null) =>
    call<Generation>("/generate", { method: "POST", body: toBody(b, file) }).then(viaProxy),
  /** 비동기 생성 시작 → id만 받고 결과 화면이 진행 상황을 조회. 예전 서버(POST /generations 없음)면 동기로 */
  startGeneration: async (b: GenerateInput, file?: File | null): Promise<string> => {
    try {
      return (await call<{ id: string }>("/generations", { method: "POST", body: toBody(b, file) })).id;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return (await real.generate(b, file)).id;
      throw e;
    }
  },
  getGeneration: (id: string) => call<Generation>(`/generations/${id}`).then(viaProxy),
  startDetailPage: (b: DetailInput, file?: File | null) =>
    call<{ id: string }>("/detail-pages", { method: "POST", body: toBody(b, file) }).then((r) => r.id),
  getDetailPage: (id: string) =>
    call<DetailPage>(`/detail-pages/${id}`).then((d) => ({ ...d, sections: d.sections.map(viaProxy) })),
  // 아래 셋은 docs/api_spec_next.md. 서빙에 아직 없으면 404 → 화면에서 대체 동작
  /** 사용 기록. 실패해도 화면에는 영향 없게 오류를 버림 */
  logEvent: (id: string, type: EventType, detail?: object) =>
    call<null>("/events", { method: "POST", body: toBody({ generation_id: id, type, detail }) }).catch(() => null),
  /** 브라우저에서 고친 그림을 서버에 저장 → 공유 링크에도 반영 */
  saveImage: (id: string, image: Blob, background?: Blob | null, message?: string) => {
    const form = new FormData();
    form.append("image", image, "image.png");
    if (background) form.append("background", background, "background.png");
    if (message) form.append("message", message);
    return call<Generation>(`/generations/${id}/image`, { method: "POST", body: form }).then(viaProxy);
  },
  getFamily: (id: string) => call<{ items: FamilyItem[] }>(`/generations/${id}/family`).then((r) => r.items.map(viaProxy)),
  regenerateSection: (id: string, index: number, adjustments: string[]) =>
    call<unknown>(`/detail-pages/${id}/sections/${index}`, {
      method: "POST",
      body: toBody({ adjustments }),
    }),
};

export const api: typeof real = USE_MOCK ? mock : real;
