import { useNotifications } from "./api";
import { DoNotDisturbCard } from "./components/DoNotDisturbCard";
import { NotificationMatrixCard } from "./components/NotificationMatrixCard";

export function NotificationsPage() {
  const { data, isLoading, isError, refetch } = useNotifications();

  if (isLoading) {
    return <NotificationsSkeleton />;
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="text-2xl font-semibold text-ink-1">알림</h2>
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
        <h2 className="text-2xl font-semibold text-ink-1">알림</h2>
        <p className="mt-1 text-sm text-ink-3">
          알림 종류별로 받을 채널을 고르고, 방해 금지 시간대를 지정하세요.
        </p>
      </header>
      <NotificationMatrixCard matrix={data.matrix} />
      <DoNotDisturbCard initial={data.doNotDisturb} />
    </div>
  );
}

function NotificationsSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-[260px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[160px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
