export type OAuthProvider = "kakao" | "naver" | "google";

const labels: Record<OAuthProvider, string> = {
  kakao: "카카오로 시작하기",
  naver: "네이버로 시작하기",
  google: "Google로 시작하기",
};

const providers: OAuthProvider[] = ["kakao", "naver", "google"];

type Props = {
  onSelect: (provider: OAuthProvider) => void;
  disabled?: boolean;
};

export function OAuthButtons({ onSelect, disabled }: Props) {
  return (
    <div className="flex flex-col gap-2">
      {providers.map((p) => (
        <button
          key={p}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(p)}
          className="flex w-full items-center justify-center border border-line-2 bg-canvas px-4 py-2.5 text-sm text-ink-1 hover:bg-fill-1 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {labels[p]}
        </button>
      ))}
    </div>
  );
}
