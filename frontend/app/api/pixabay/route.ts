// 사진을 안 올린 사장님께 보여 줄 Pixabay 참고 사진. 키를 브라우저에 노출하지 않으려고 서버에서 부름
// GET ?q=소금빵 → { hits: [{ id, thumb, page, user }] } / GET ?id=123 → 고른 사진 바이트 (참고 사진으로 업로드)
// Pixabay 약관: 검색 결과 24시간 캐시, 계속 쓸 사진은 핫링크 말고 내려받아 쓰기, 출처(Pixabay) 표시
import { NextResponse, type NextRequest } from "next/server";

const API = "https://pixabay.com/api/";
const DAY = 60 * 60 * 24;

interface Hit {
  id: number;
  webformatURL: string;
  largeImageURL: string;
  pageURL: string;
  user: string;
}

async function search(params: Record<string, string>): Promise<Hit[]> {
  const key = process.env.PIXABAY_API_KEY;
  if (!key) return []; // 키 없으면 사진 고르기를 건너뛰고 업로드 안내만
  const qs = new URLSearchParams({ key, image_type: "photo", safesearch: "true", lang: "ko", ...params });
  const res = await fetch(`${API}?${qs}`, { next: { revalidate: DAY } });
  if (!res.ok) return [];
  return ((await res.json()) as { hits?: Hit[] }).hits ?? [];
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim().slice(0, 100);
  const id = req.nextUrl.searchParams.get("id");

  if (id) {
    if (!/^\d{1,12}$/.test(id)) return NextResponse.json({ detail: "잘못된 사진이에요." }, { status: 400 });
    const [hit] = await search({ id });
    const img = hit && (await fetch(hit.largeImageURL, { next: { revalidate: DAY } }));
    if (!img || !img.ok) return NextResponse.json({ detail: "사진을 받지 못했어요. 다른 사진을 골라 주세요." }, { status: 502 });
    return new NextResponse(img.body, { headers: { "Content-Type": img.headers.get("Content-Type") ?? "image/jpeg" } });
  }

  if (!q) return NextResponse.json({ hits: [] });
  const hits = await search({ q, per_page: "8" });
  return NextResponse.json(
    { hits: hits.map((h) => ({ id: h.id, thumb: h.webformatURL, page: h.pageURL, user: h.user })) },
    { headers: { "Cache-Control": `public, max-age=${DAY}` } },
  );
}
