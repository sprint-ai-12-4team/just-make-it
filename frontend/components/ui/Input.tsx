import { cn } from "@/lib/utils";
import { InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, hint, id, ...props }, ref) => {
    const inputId = id || props.name;
    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-slate-700"
          >
            {label}
            {props.required && (
              <span className="ml-0.5 text-red-500">*</span>
            )}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "flex h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:cursor-not-allowed disabled:opacity-50",
            className
          )}
          {...props}
        />
        {hint && <p className="text-xs text-slate-500">{hint}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
