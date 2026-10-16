"use client";

import { GenerationModeSelector } from "@/components/GenerationModeSelector";
import { InfoForm } from "@/components/InfoForm";
import { Button } from "@/components/ui/Button";
import {
  generateImage,
  loadDraft,
  saveDraft,
  saveResult,
} from "@/lib/api";
import type { GenerationMode, Purpose } from "@/lib/types";
import { PURPOSE_OPTIONS } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function CreatePage() {
  const router = useRouter();
  const [purpose, setPurpose] = useState<Purpose | null>(null);
  const [productName, setProductName] = useState("");
  const [message, setMessage] = useState("");
  const [style, setStyle] = useState("");
  const [generationMode, setGenerationMode] =
    useState<GenerationMode>("quick");
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const draft = loadDraft();
    if (!draft?.purpose) {
      router.replace("/");
      return;
    }
    setPurpose(draft.purpose as Purpose);
    if (draft.productName) setProductName(draft.productName);
    if (draft.message) setMessage(draft.message);
    if (draft.style) setStyle(draft.style);
    if (draft.generationMode) setGenerationMode(draft.generationMode);
  }, [router]);

  const purposeLabel =
    PURPOSE_OPTIONS.find((p) => p.id === purpose)?.title ?? "";

  const canSubmit =
    !!purpose && productName.trim().length > 0 && message.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !purpose) return;

    setError(null);
    setLoading(true);

    const payload = {
      purpose,
      productName: productName.trim(),
      message: message.trim(),
      style: style || undefined,
      generationMode,
      referenceImage,
    };

    saveDraft(payload);

    try {
      // MVP: 백엔드가 아직 없을 수 있으므로 목 응답 처리
      // 실제 연동 시 generateImage만 사용하면 됨
      let result;
      try {
        result = await generateImage(payload);
      } catch {
        // 개발 중 백엔드 미기동 시 데모 결과
        result = {
          status: "success" as const,
          image_url:
            "https://placehold.co/1024x1024/e2e8f0/64748b?text=Demo+Ad+Image",
          generation_source: "local" as const,
        };
      }

      if (result.status === "success") {
        saveResult({
          imageUrl: result.image_url,
          source: result.generation_source,
          productName: payload.productName,
          message: payload.message,
          purpose: purposeLabel,
        });
        router.push("/result");
      } else {
        setError("생성이 진행 중입니다. 잠시 후 다시 시도해 주세요.");
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "이미지 생성에 실패했습니다."
      );
    } finally {
      setLoading(false);
    }
  }

  if (!purpose) {
    return (
      <div className="flex justify-center py-20 text-slate-500">불러오는 중…</div>
    );
  }

  return (
    <main>
      <div className="mb-6">
        <button
          type="button"
          onClick={() => router.push("/")}
          className="text-sm text-slate-500 hover:text-slate-800"
        >
          ← 목적 다시 선택
        </button>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
          정보를 알려 주세요
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          선택하신 용도: <span className="font-medium">{purposeLabel}</span>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        <InfoForm
          productName={productName}
          message={message}
          style={style}
          onProductNameChange={setProductName}
          onMessageChange={setMessage}
          onStyleChange={setStyle}
          onReferenceImageChange={setReferenceImage}
        />

        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-700">
            생성 방식
          </h2>
          <GenerationModeSelector
            value={generationMode}
            onChange={setGenerationMode}
          />
        </section>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <Button
          type="submit"
          className="w-full"
          size="lg"
          disabled={!canSubmit}
          loading={loading}
        >
          {loading ? "이미지 만드는 중…" : "이미지 만들기"}
        </Button>

        {loading && (
          <p className="text-center text-sm text-slate-500">
            보통 10~30초 정도 걸려요. 잠시만 기다려 주세요.
          </p>
        )}
      </form>
    </main>
  );
}
