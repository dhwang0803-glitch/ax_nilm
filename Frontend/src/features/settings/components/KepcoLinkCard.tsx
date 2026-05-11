import type { AccountKepco } from "../types";

type Props = { kepco: AccountKepco };

const CONTRACT_LABEL = "계약 종별";

export function KepcoLinkCard({ kepco }: Props) {
  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="kepco-card-heading"
    >
      <header className="flex items-center justify-between">
        <h3 id="kepco-card-heading" className="text-base font-semibold text-ink-1">
          한전 연동
        </h3>
        <button
          type="button"
          className="bg-fill-2 px-3 py-1 text-xs text-ink-2"
          onClick={() => alert("준비 중입니다")}
        >
          재연동
        </button>
      </header>
      <dl className="mt-4 grid grid-cols-[120px_1fr] gap-y-3 text-sm">
        <dt className="text-ink-3">고객번호</dt>
        <dd className="font-mono text-ink-1">{kepco.customerNo}</dd>
        <dt className="text-ink-3">주소</dt>
        <dd className="text-ink-1">{kepco.addressMasked}</dd>
        <dt className="text-ink-3">{CONTRACT_LABEL}</dt>
        <dd className="text-ink-1">{kepco.contractType}</dd>
        <dt className="text-ink-3">연동일</dt>
        <dd className="text-ink-1">{kepco.linkedAt}</dd>
      </dl>
    </section>
  );
}
