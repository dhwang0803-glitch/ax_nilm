-- 더미 historical 적재 결과 sanity 검증
\echo '== 전체 행수 + 기간 =='
SELECT count(*) AS rows,
       count(DISTINCT household_id) AS households,
       count(DISTINCT day) AS days,
       min(day) AS min_day,
       max(day) AS max_day,
       sum(kwh)::numeric(12,2) AS total_kwh
  FROM power_daily_historical;

\echo '== 가구별 분포 (절감률·평균 kWh) =='
SELECT household_id,
       savings_rate,
       count(*) AS days,
       round(avg(kwh)::numeric, 2) AS mean_kwh,
       round(min(kwh)::numeric, 2) AS min_kwh,
       round(max(kwh)::numeric, 2) AS max_kwh,
       round(stddev(kwh)::numeric, 2) AS std_kwh
  FROM power_daily_historical
 GROUP BY household_id, savings_rate
 ORDER BY savings_rate, household_id;

\echo '== 절감률 분포 (시연 캐시백 단가 구간) =='
SELECT savings_rate,
       count(DISTINCT household_id) AS households,
       count(*) AS rows
  FROM power_daily_historical
 GROUP BY savings_rate
 ORDER BY savings_rate;

\echo '== 월별 계절성 검증 (전 가구 평균) =='
SELECT extract(month FROM day)::int AS month,
       count(*) AS rows,
       round(avg(kwh)::numeric, 2) AS mean_kwh
  FROM power_daily_historical
 GROUP BY extract(month FROM day)
 ORDER BY month;

\echo '== 결정론 sanity (특정 가구·날짜 seed 일치) =='
SELECT household_id, day, kwh, seed_value
  FROM power_daily_historical
 WHERE household_id = 'H011' AND day IN ('2024-05-15', '2024-05-16', '2024-05-17')
 ORDER BY day;
