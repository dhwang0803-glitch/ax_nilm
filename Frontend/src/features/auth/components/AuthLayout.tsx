import type { ReactNode } from "react";
import { BrandPanel } from "./BrandPanel";

type Props = {
  brandTitle: string;
  children: ReactNode;
};

export function AuthLayout({ brandTitle, children }: Props) {
  return (
    <div className="grid min-h-screen grid-cols-2 bg-bg">
      <BrandPanel title={brandTitle} />
      <div className="flex items-center justify-center bg-canvas px-12 py-16">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
