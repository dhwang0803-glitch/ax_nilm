import type { AccountProfile } from "../types";

type Props = { profile: AccountProfile };

export function ProfileCard({ profile }: Props) {
  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="profile-card-heading"
    >
      <header className="flex items-center justify-between">
        <h3 id="profile-card-heading" className="text-base font-semibold text-ink-1">
          프로필
        </h3>
        <button
          type="button"
          className="bg-fill-2 px-3 py-1 text-xs text-ink-2"
          onClick={() => alert("준비 중입니다")}
        >
          수정
        </button>
      </header>
      <dl className="mt-4 grid grid-cols-[120px_1fr] gap-y-3 text-sm">
        <dt className="text-ink-3">이름</dt>
        <dd className="text-ink-1">{profile.name}</dd>
        <dt className="text-ink-3">이메일</dt>
        <dd className="text-ink-1">{profile.email}</dd>
        <dt className="text-ink-3">휴대폰</dt>
        <dd className="text-ink-1">{profile.phone}</dd>
        <dt className="text-ink-3">구성원</dt>
        <dd className="text-ink-1">{profile.memberCount}명</dd>
      </dl>
    </section>
  );
}
