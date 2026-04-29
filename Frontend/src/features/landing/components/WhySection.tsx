type Feature = { title: string; desc: string };

const features: Feature[] = [
  { title: "가전별 분해", desc: "단일 분전반에서 NILM으로 가전별 사용량 추정" },
  { title: "주간/월간 추적", desc: "지난 주 동일 요일과 매주 비교" },
  { title: "AI 진단", desc: "이상 징후 자동 알림 + 절약 추천" },
];

export function WhySection() {
  return (
    <section id="features" className="px-10 py-16">
      <div className="mx-auto max-w-[1280px]">
        <h2 className="text-2xl font-semibold text-ink-1">왜 에너지캐시백인가</h2>
        <div className="mt-6 grid grid-cols-3 gap-4">
          {features.map((f) => (
            <article key={f.title} className="border border-line-2 bg-canvas p-4">
              <div className="placeholder-img mb-3 h-20">ICON</div>
              <h3 className="text-sm font-semibold text-ink-1">{f.title}</h3>
              <p className="mt-1 text-[13px] text-ink-3">{f.desc}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
