/** 광고 목적(매체) */
export type Purpose =
  | "instagram"
  | "commerce"
  | "youtube"
  | "kakao"
  | "free";

/** 생성 방식 */
export type GenerationMode = "quick" | "template" | "canvas";

export interface PurposeOption {
  id: Purpose;
  title: string;
  description: string;
  aspectHint: string;
}

export interface GenerationModeOption {
  id: GenerationMode;
  title: string;
  description: string;
  recommended?: boolean;
}

/** 생성 요청에 쓰는 폼 데이터 */
export interface CreateFormData {
  purpose: Purpose;
  productName: string;
  message: string;
  style?: string;
  generationMode: GenerationMode;
  /** 참고 이미지는 나중에 FormData로 전송 */
  referenceImage?: File | null;
}

/** FastAPI /generate 응답 (초안) */
export interface GenerateSuccessResponse {
  status: "success";
  image_url: string;
  generation_source: "local" | "openai";
}

export interface GenerateProcessingResponse {
  status: "processing";
  job_id: string;
}

export type GenerateResponse =
  | GenerateSuccessResponse
  | GenerateProcessingResponse;

export const PURPOSE_OPTIONS: PurposeOption[] = [
  {
    id: "instagram",
    title: "인스타그램",
    description: "피드·스토리에 올릴 이미지",
    aspectHint: "정사각 / 세로",
  },
  {
    id: "commerce",
    title: "스마트스토어 · 쿠팡",
    description: "상품 썸네일·상세 이미지",
    aspectHint: "상품 중심",
  },
  {
    id: "youtube",
    title: "유튜브 썸네일",
    description: "클릭을 유도하는 강한 썸네일",
    aspectHint: "16:9",
  },
  {
    id: "kakao",
    title: "카카오톡 · 문자",
    description: "메시지에 첨부할 홍보 이미지",
    aspectHint: "세로 / 정사각",
  },
  {
    id: "free",
    title: "자유롭게 만들기",
    description: "용도에 맞춰 직접 설정",
    aspectHint: "자유",
  },
];

export const GENERATION_MODE_OPTIONS: GenerationModeOption[] = [
  {
    id: "quick",
    title: "빠른 생성",
    description: "텍스트까지 한 장에 바로 만들어 드려요",
    recommended: true,
  },
  {
    id: "template",
    title: "템플릿 사용",
    description: "미리 만든 레이아웃에 맞춰 생성해요",
  },
  {
    id: "canvas",
    title: "직접 편집",
    description: "이미지와 글자를 따로 만든 뒤 배치해요",
  },
];

export const STYLE_CHIPS = [
  "밝고 경쾌한",
  "고급스러운",
  "따뜻한",
  "심플한",
  "강렬한",
] as const;
