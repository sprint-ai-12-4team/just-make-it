"use client";

import { PURPOSE_OPTIONS, type Purpose } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Instagram,
  ShoppingBag,
  Youtube,
  MessageCircle,
  Sparkles,
} from "lucide-react";

const icons: Record<Purpose, React.ReactNode> = {
  instagram: <Instagram className="h-6 w-6" />,
  commerce: <ShoppingBag className="h-6 w-6" />,
  youtube: <Youtube className="h-6 w-6" />,
  kakao: <MessageCircle className="h-6 w-6" />,
  free: <Sparkles className="h-6 w-6" />,
};

interface PurposeSelectorProps {
  value?: Purpose;
  onChange: (purpose: Purpose) => void;
}

export function PurposeSelector({ value, onChange }: PurposeSelectorProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {PURPOSE_OPTIONS.map((opt) => {
        const selected = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            className={cn(
              "flex items-start gap-3 rounded-2xl border p-4 text-left transition-all",
              selected
                ? "border-brand-500 bg-brand-50 ring-2 ring-brand-500/30"
                : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
            )}
          >
            <span
              className={cn(
                "mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                selected
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 text-slate-600"
              )}
            >
              {icons[opt.id]}
            </span>
            <span className="min-w-0">
              <span className="block font-semibold text-slate-900">
                {opt.title}
              </span>
              <span className="mt-0.5 block text-sm text-slate-600">
                {opt.description}
              </span>
              <span className="mt-1 inline-block text-xs text-slate-400">
                {opt.aspectHint}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
