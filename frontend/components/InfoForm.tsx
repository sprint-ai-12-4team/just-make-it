"use client";

import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { STYLE_CHIPS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useRef, useState } from "react";
import { ImagePlus, X } from "lucide-react";

interface InfoFormProps {
  productName: string;
  message: string;
  style: string;
  onProductNameChange: (v: string) => void;
  onMessageChange: (v: string) => void;
  onStyleChange: (v: string) => void;
  onReferenceImageChange: (file: File | null) => void;
}

export function InfoForm({
  productName,
  message,
  style,
  onProductNameChange,
  onMessageChange,
  onStyleChange,
  onReferenceImageChange,
}: InfoFormProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);

  function handleFile(file: File | null) {
    onReferenceImageChange(file);
    if (preview) URL.revokeObjectURL(preview);
    if (file) {
      setPreview(URL.createObjectURL(file));
    } else {
      setPreview(null);
    }
  }

  return (
    <div className="space-y-5">
      <Input
        label="가게 · 상품 이름"
        name="productName"
        placeholder="예: 청담동 카페 라떼"
        value={productName}
        onChange={(e) => onProductNameChange(e.target.value)}
        required
      />

      <Textarea
        label="핵심 메시지 · 키워드"
        name="message"
        placeholder="예: 주말 20% 할인, 신메뉴 출시, 오픈 이벤트"
        value={message}
        onChange={(e) => onMessageChange(e.target.value)}
        required
        hint="짧게 적어도 됩니다. 홍보 문구는 나중에 다듬을 수 있어요."
      />

      <div className="space-y-2">
        <p className="text-sm font-medium text-slate-700">분위기 · 스타일</p>
        <div className="flex flex-wrap gap-2">
          {STYLE_CHIPS.map((chip) => {
            const selected = style === chip;
            return (
              <button
                key={chip}
                type="button"
                onClick={() => onStyleChange(selected ? "" : chip)}
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-sm transition-colors",
                  selected
                    ? "bg-brand-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                )}
              >
                {chip}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium text-slate-700">
          참고 이미지 <span className="font-normal text-slate-400">(선택)</span>
        </p>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            handleFile(f);
          }}
        />
        {preview ? (
          <div className="relative inline-block">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={preview}
              alt="참고 이미지"
              className="h-28 w-28 rounded-xl object-cover ring-1 ring-slate-200"
            />
            <button
              type="button"
              onClick={() => {
                handleFile(null);
                if (fileRef.current) fileRef.current.value = "";
              }}
              className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-slate-900 text-white shadow"
              aria-label="이미지 제거"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex h-28 w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 text-slate-500 hover:border-brand-400 hover:bg-brand-50 hover:text-brand-600"
          >
            <ImagePlus className="h-6 w-6" />
            <span className="text-sm">상품 사진 · 로고 업로드</span>
          </button>
        )}
      </div>
    </div>
  );
}
