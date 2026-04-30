import { useSecurity } from "./api";
import { DangerZoneCard } from "./components/DangerZoneCard";
import { PasswordCard } from "./components/PasswordCard";
import { SessionsCard } from "./components/SessionsCard";
import { TwoFactorCard } from "./components/TwoFactorCard";

export function SecurityPage() {
  const { data, isLoading, isError, refetch } = useSecurity();

  if (isLoading) {
    return <SecuritySkeleton />;
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="text-2xl font-semibold text-ink-1">보안</h2>
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
      <header>
        <h2 className="text-2xl font-semibold text-ink-1">보안</h2>
        <p className="mt-1 text-sm text-ink-3">
          비밀번호·2단계 인증·활성 세션을 관리하고, 필요 시 계정을 삭제할 수 있습니다.
        </p>
      </header>
      <PasswordCard />
      <TwoFactorCard initialEnabled={data.twoFactorEnabled} />
      <SessionsCard sessions={data.sessions} />
      <DangerZoneCard />
    </div>
  );
}

function SecuritySkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-[220px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[140px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[200px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[140px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
