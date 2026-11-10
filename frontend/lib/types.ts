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
  keep_product?: boolean; // 상품 사진 그대로, 배경 장면만 AI (api_spec_next 4장)
  consult_id?: string; // AI 상담에서 넘어왔으면 (api_spec_consult 3-4). 모르는 서버는 무시함
  reference_source?: "upload" | "stock"; // 참고 사진 출처 (api_spec_next2 2-2). 사진 없으면 안 보냄
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
  created_at?: string;
  edited?: boolean;
  progress?: GenProgress | null; // status가 processing일 때 (api_spec V3)
  product_url?: string | null; // keep_product일 때 배경이 투명한 상품. 프론트가 장면 위에 합침 // 브라우저에서 고친 그림을 서버에 저장했으면 true
  input?: Omit<GenerateInput, "parent_id">;
}

/** 비동기 생성 진행 상황 (GET /generations/{id}) */
export interface GenProgress {
  stage: "queued" | "running";
  jobs_ahead: number;
  estimated_seconds: number;
  // 아래는 api_spec_consult 1장. 예전 서버는 안 보냄
  elapsed_seconds?: number;
  overdue?: boolean;
  phase?: "text" | "image" | "saving" | null;
  step?: number | null;
  steps?: number | null;
}

/** 사용 기록 종류 (docs/api_spec_next.md 1장 + api_spec_consult 5장) */
export type EventType = "download" | "copy_link" | "remake" | "edit_text" | "cutout" | "pick_copy" | "add_qr" | "tip_click" | "copy_kit";

/** 대기 중 정보 카드 (api_spec_consult 2장) */
export interface Tip {
  id: string;
  kind: "season" | "howto" | "platform" | "law" | "support" | "news";
  title: string;
  body: string | null;
  action?: { label: string; href: string } | null;
  source?: { name: string; url: string } | null;
}

/** AI 상담 결과 = 광고 기획서 (api_spec_consult 3장). 쓰는 건 terra 1회 */
export interface Brief {
  category: string;
  goal: string;
  product_name: string;
  period: string | null; // 행사 기간. 사장님이 답한 그대로 (지어내지 않음)
  strengths: string[];
  audience: string;
  purpose: Purpose; // 만들기 화면 목적 (크기)
  channel: string;
  message: string; // 핵심 메시지
  copies: string[]; // 그림에 넣을 문구 2안
  style: string | null;
  reason: string; // 이렇게 제안하는 이유
  next_tips: string[];
}

export interface ConsultMessage {
  role: "assistant" | "user";
  text: string;
  chips?: string[];
}

/** 상담 한 턴의 응답 */
export interface ConsultTurn {
  id: string;
  reply: string;
  chips: string[];
  allow_free_text: boolean;
  turn: number;
  max_turns: number;
  brief: Brief | null;
  ended?: boolean;
  edits_left?: number; // 기획서를 더 고칠 수 있는 횟수 (제안 2회)
}

export interface Consult {
  id: string;
  messages: ConsultMessage[];
  brief: Brief | null;
  ended?: boolean;
  edits_left?: number;
}

export type ConvertFormat =
  | "instagram_post"
  | "instagram_hashtags"
  | "instagram_location"
  | "instagram_story"
  | "naver_coupon"
  | "naver_blog_title"
  | "store_description";

export type ConvertResult = string | string[] | { title: string; condition: string; period: string };

/** 게시 문구 키트 1차 형식. 채널별로 묶어서 보여 줌 */
export const CONVERT_FORMATS: { id: ConvertFormat; title: string; channel: string }[] = [
  { id: "instagram_post", title: "본문", channel: "인스타그램" },
  { id: "instagram_hashtags", title: "해시태그", channel: "인스타그램" },
  { id: "instagram_location", title: "위치 태그 후보", channel: "인스타그램" },
  { id: "instagram_story", title: "스토리 한 줄", channel: "인스타그램" },
  { id: "naver_coupon", title: "쿠폰 문구", channel: "네이버" },
  { id: "naver_blog_title", title: "블로그 제목 3개", channel: "네이버" },
  { id: "store_description", title: "상품 설명", channel: "스마트스토어 · 쿠팡" },
];

export interface FamilyItem {
  id: string;
  parent_id: string | null;
  image_url: string;
  created_at?: string;
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

// 서버로 보내는 칩. 글자 크기·위치는 글자 직접 고치기(canvas)에서 처리
export const ADJUSTMENTS = ["더 밝게", "배경 단순하게", "텍스트 짧게"];

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

/** GET /stats 한 행 (api_spec "GET /stats"). 뒤쪽 칸은 서빙 미구현이라 없을 수 있음 */
export interface RefStats { generated: number; download_rate: number; remake_rate: number }
export interface DailyStats {
  date: string; generated: number; downloaded: number; edited: number; remade: number;
  download_rate: number; edit_rate: number; remake_rate: number;
  seconds_p50?: number | null; seconds_p95?: number | null; local_rate?: number | null;
  cost_usd?: number | null; cost_per_image_usd?: number | null; error_rate?: number | null;
  by_reference?: { upload: RefStats; stock: RefStats; none: RefStats };
}
export interface Stats { days: DailyStats[]; total: DailyStats }

/** public/eval/summary.json (모델 오프라인 평가. make_report.py가 만듦). 숫자는 null 가능 */
export interface EvalRun {
  run_id: string; cases: number; avg_seconds: number | null; p95_seconds: number | null; cost_usd: number | null;
  fallback_rate: number | null; clip_score: number | null; ref_similarity: number | null; ocr_match: number | null;
}
export interface EvalSummary { generated_at: string; runs: EvalRun[] }
