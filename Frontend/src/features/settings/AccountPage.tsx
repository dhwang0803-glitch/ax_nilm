import { useAccount } from "./api";
import { KepcoLinkCard } from "./components/KepcoLinkCard";
import { ProfileCard } from "./components/ProfileCard";

export function AccountPage() {
  const { data, isLoading, isError, refetch } = useAccount();

  if (isLoading) {
    return <AccountSkeleton />;
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="text-2xl font-semibold text-ink-1">프로필 / 한전 연동</h2>
        </header>
        <div className="border border-line-2 bg-canvas p-6">
          <p className="text-sm text-ink-2">데이터를 불러올 수 없습니다.</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-3 border border-ink-1 bg-ink-1 px-3 py-1.5 text-xs text-canvas"
          >
            재시도
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ProfileCard profile={data.profile} />
      <KepcoLinkCard kepco={data.kepco} />
    </div>
  );
}

function AccountSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-[180px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[200px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
