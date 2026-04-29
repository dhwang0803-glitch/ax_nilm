import { forwardRef } from "react";
import type { ComponentPropsWithoutRef } from "react";

type Props = ComponentPropsWithoutRef<"input"> & {
  label: string;
  error?: string;
};

export const Field = forwardRef<HTMLInputElement, Props>(function Field(
  { label, error, id, className = "", ...rest },
  ref
) {
  const inputId = id ?? `field-${rest.name ?? label}`;
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={inputId}
        className="font-mono text-[10px] uppercase tracking-wider text-ink-3"
      >
        {label}
      </label>
      <input
        id={inputId}
        ref={ref}
        className={`border border-line-2 bg-canvas px-3 py-2 text-sm text-ink-1 placeholder:text-ink-4 focus:border-ink-1 focus:outline-none disabled:bg-fill-1 disabled:text-ink-3 ${className}`}
        {...rest}
      />
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
});
