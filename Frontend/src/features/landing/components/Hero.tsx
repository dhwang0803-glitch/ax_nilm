import { Link } from "react-router-dom";

export function Hero() {
  return (
    <section className="border-b border-line-2 bg-canvas px-10 py-20 text-center">
      <span className="inline-block bg-fill-2 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-2">
        베타
      </span>
      <h1 className="mx-auto mt-4 max-w-[800px] text-5xl font-bold leading-[1.1] tracking-tight text-ink-1">
        매달 받는 캐시백,
        <br />
        이번 달은 얼마일까?
      </h1>
      <p className="mx-auto mt-3 max-w-[540px] text-[15px] text-ink-2">
        한전 고객번호 한 번 등록하면, 매달 절감 금액을 자동으로 계산해 드립니다.
      </p>
      <div className="mt-6 flex justify-center">
        <Link
          to="/auth/login"
          className="inline-flex items-center border border-ink-1 bg-ink-1 px-4 py-2 text-sm font-medium text-canvas"
        >
          시작하기 · 무료
        </Link>
      </div>
      <div className="mx-auto mt-14 max-w-[1100px]">
        <div className="placeholder-img h-[360px]">FULL DASHBOARD MOCK</div>
      </div>
    </section>
  );
}
