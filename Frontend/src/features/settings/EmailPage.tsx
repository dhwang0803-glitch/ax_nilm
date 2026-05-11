import { useEmail } from "./api";
import { AdvancedSmtpDisclosure } from "./components/AdvancedSmtpDisclosure";
import { EmailNotificationToggleCard } from "./components/EmailNotificationToggleCard";
import { EmailRecipientCard } from "./components/EmailRecipientCard";
import { EmailTestCard } from "./components/EmailTestCard";

export function EmailPage() {
  const { data, isLoading, isError, refetch } = useEmail();

  if (isLoading) return <EmailSkeleton />;

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="text-2xl font-semibold text-ink-1">이메일 연동</h2>
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
        <h2 className="text-2xl font-semibold text-ink-1">이메일 연동</h2>
        <p className="mt-1 text-sm text-ink-3">
          이상 탐지·캐시백 알림을 받을 이메일 설정입니다.
        </p>
      </header>
      <EmailRecipientCard
        primaryEmail={data.primaryEmail}
        initialAlternate={data.alternateEmail}
      />
      <EmailNotificationToggleCard initial={data.toggles} />
      <EmailTestCard lastTestAt={data.lastTestAt} />
      <AdvancedSmtpDisclosure />
    </div>
  );
}

function EmailSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-[160px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[260px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[140px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[60px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
