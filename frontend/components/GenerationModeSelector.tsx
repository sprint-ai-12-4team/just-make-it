"use client";

import {
  GENERATION_MODE_OPTIONS,
  type GenerationMode,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface GenerationModeSelectorProps {
  value: GenerationMode;
  onChange: (mode: GenerationMode) => void;
}

export function GenerationModeSelector({
  value,
  onChange,
}: GenerationModeSelectorProps) {
  return (
    <div className="space-y-2">
      {GENERATION_MODE_OPTIONS.map((opt) => {
        const selected = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            className={cn(
              "flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-all",
              selected
                ? "border-brand-500 bg-brand-50 ring-2 ring-brand-500/20"
                : "border-slate-200 bg-white hover:border-slate-300"
            )}
          >
            <span>
              <span className="flex items-center gap-2 font-medium text-slate-900">
                {opt.title}
                {opt.recommended && (
                  <span className="rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                    추천
                  </span>
                )}
              </span>
              <span className="mt-0.5 block text-sm text-slate-500">
                {opt.description}
              </span>
            </span>
            <span
              className={cn(
                "h-4 w-4 shrink-0 rounded-full border-2",
                selected
                  ? "border-brand-600 bg-brand-600"
                  : "border-slate-300"
              )}
            />
          </button>
        );
      })}
    </div>
  );
}
