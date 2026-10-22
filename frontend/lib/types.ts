// 계약: docs/api_spec.md. 필드 이름은 API 그대로 snake_case

export type Purpose = "instagram" | "commerce" | "youtube" | "kakao" | "free";
export type Status = "processing" | "success" | "error";
export type ImageModel = "flux2-klein-4b" | "openai-image-2.5-flare";
export type TextModel = "gemma-4-12b-it" | "openai-gpt-5.6-luna";

export interface GenerateInput {
  purpose: Purpose;
  product_name: string;
  message: string;
  style: string | null;
  adjustments: string[];
  parent_id: string | null;
  image_model: ImageModel;
}

export type TextPosition = "top" | "middle" | "bottom";
export type FontId = "jua" | "yeonsung" | "batang" | "dodum" | "blackhan";

/** 서버가 얹은 글자 위치·글꼴·크기 (api_spec 5장) */
export interface TextLayout {
  position: TextPosition;
  font: FontId;
  size_scale: number;
}

export interface Generation {
  id: string;
  status: Status;
  image_url: string; // 글자 얹은 최종 이미지 (text_layout이 없는 예전 결과는 글자 없는 이미지)
  background_url?: string | null;
  message: string;
  text_layout?: TextLayout | null;
  source: string; // 화면 노출 금지
  width: number;
  height: number;
  parent_id?: string | null;
  input?: Omit<GenerateInput, "parent_id">;
}

export interface DetailInput {
  product_name: string;
  message: string;
  features: string[];
  style: string | null;
  image_model: ImageModel;
}

export interface Section {
  index: number;
  role: "hero" | "feature" | "closing";
  status: "pending" | Status;
  title: string | null;
  body: string | null;
  image_url: string | null;
}

export interface DetailPage {
  id: string;
  status: Status;
  progress: { done: number; total: number };
  sections: Section[];
}

export const PURPOSES: { id: Purpose; title: string; desc: string }[] = [
  { id: "instagram", title: "인스타그램", desc: "피드에 올릴 정사각형 이미지" },
  { id: "commerce", title: "스마트스토어 · 쿠팡", desc: "상품 대표 이미지나 상세페이지" },
  { id: "youtube", title: "유튜브 썸네일", desc: "눈에 띄는 가로형 썸네일" },
  { id: "kakao", title: "카카오톡 · 문자", desc: "메시지에 붙일 세로형 이미지" },
  { id: "free", title: "자유롭게 만들기", desc: "어디든 쓸 수 있는 정사각형" },
];

export const STYLES = ["밝고 경쾌한", "고급스러운", "따뜻한", "심플한", "강렬한"];

// 서버로 보내는 칩. "글자 더 크게"는 글자 고치기(size_scale)에서 처리
export const ADJUSTMENTS = ["더 밝게", "배경 단순하게", "텍스트 짧게"];

export const POSITIONS: [TextPosition, string][] = [["top", "위"], ["middle", "가운데"], ["bottom", "아래"]];
export const FONTS: [FontId, string][] = [
  ["jua", "주아"], ["yeonsung", "연성"], ["batang", "고운바탕"], ["dodum", "고운돋움"], ["blackhan", "검은고딕"],
];
export const BIG_TEXT = 1.25;

export const SIZES: Record<Purpose, [number, number]> = {
  instagram: [1024, 1024],
  commerce: [1024, 1024],
  youtube: [1536, 864],
  kakao: [1024, 1536],
  free: [1024, 1024],
};

// 화면에는 모델 이름을 노출하지 않음 (title·desc만 보여줌)
// ponytail: 고정 목록. 서버에 GET /models가 생기면 거기서 받아오기 (api_spec 6장)
export const IMAGE_MODELS: { id: ImageModel; title: string; desc: string }[] = [
  { id: "flux2-klein-4b", title: "빠르게", desc: "기본 · 몇 초면 완성" },
  { id: "openai-image-2.5-flare", title: "더 정교하게", desc: "조금 더 걸려요" },
];
export const TEXT_MODELS: { id: TextModel; title: string; desc: string }[] = [
  { id: "gemma-4-12b-it", title: "기본", desc: "빠른 문구 추천" },
  { id: "openai-gpt-5.6-luna", title: "더 자연스럽게", desc: "문장을 더 다듬어 드려요" },
];
