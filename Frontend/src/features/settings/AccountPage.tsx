export function AccountPage() {
  return (
    <div className="flex flex-col gap-4">
      <section className="border border-line-2 bg-canvas p-6">
        <h3 className="text-base font-semibold">프로필</h3>
        <p className="mt-2 text-sm text-ink-3">
          Phase 06-A 에서 본 구현 (이름·이메일·휴대폰·구성원)
        </p>
      </section>
      <section className="border border-line-2 bg-canvas p-6">
        <h3 className="text-base font-semibold">한전 연동</h3>
        <p className="mt-2 text-sm text-ink-3">
          Phase 06-A 에서 본 구현 (고객번호·주소·계약·연동일)
        </p>
      </section>
    </div>
  );
}
