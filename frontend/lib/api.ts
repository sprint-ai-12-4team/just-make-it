import type { CreateFormData, GenerateResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * 이미지 생성 요청
 * - 참고 이미지가 있으면 multipart, 없으면 JSON
 * - 실제 FastAPI 스펙이 확정되면 필드명만 맞추면 됨
 */
export async function generateImage(
  data: CreateFormData
): Promise<GenerateResponse> {
  const hasFile = data.referenceImage instanceof File;

  if (hasFile) {
    const form = new FormData();
    form.append("purpose", data.purpose);
    form.append("product_name", data.productName);
    form.append("message", data.message);
    form.append("generation_mode", data.generationMode);
    if (data.style) form.append("style", data.style);
    form.append("reference_image", data.referenceImage as File);

    const res = await fetch(`${API_BASE}/generate`, {
      method: "POST",
      body: form,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `생성 요청 실패 (${res.status})`);
    }
    return res.json();
  }

  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      purpose: data.purpose,
      product_name: data.productName,
      message: data.message,
      style: data.style ?? null,
      generation_mode: data.generationMode,
      reference_image_url: null,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `생성 요청 실패 (${res.status})`);
  }
  return res.json();
}

/** 세션에 임시 저장 (페이지 간 전달용, MVP) */
const STORAGE_KEY = "jmi_create_draft";

export function saveDraft(data: Partial<CreateFormData> & { purpose: string }) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function loadDraft(): (Partial<CreateFormData> & { purpose?: string }) | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearDraft() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(STORAGE_KEY);
}

const RESULT_KEY = "jmi_last_result";

export function saveResult(payload: {
  imageUrl: string;
  source: string;
  productName: string;
  message: string;
  purpose: string;
}) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(RESULT_KEY, JSON.stringify(payload));
}

export function loadResult() {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(RESULT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as {
      imageUrl: string;
      source: string;
      productName: string;
      message: string;
      purpose: string;
    };
  } catch {
    return null;
  }
}
