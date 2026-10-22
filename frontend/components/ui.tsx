import clsx from "clsx";
import { AlertCircle, Loader2 } from "lucide-react";

/** 오류·안내. 빨강 대신 노랑 바탕 + 아이콘 + 문장 (DESIGN.md: 색 추가 금지) */
export function Notice({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-btn bg-honey p-4">
      <AlertCircle aria-hidden className="size-6 shrink-0" />
      <p className="flex-1 font-medium">{children}</p>
      {action}
    </div>
  );
}

/** 오래 걸리는 작업 대기 화면 */
export function Waiting({ title, hint }: { title: string; hint: string }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center gap-4 rounded-card bg-honey px-6 py-16 text-center">
      <Loader2 aria-hidden className="size-12 animate-spin" />
      <p className="text-h-sm font-bold">{title}</p>
      <p>{hint}</p>
    </div>
  );
}

export function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} className={clsx("chip", on && "chip-on")}>
      {children}
    </button>
  );
}

export function FieldError({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <p id={id} className="mt-2 flex items-center gap-1.5 font-medium">
      <AlertCircle aria-hidden className="size-5 shrink-0" /> {children}
    </p>
  );
}
