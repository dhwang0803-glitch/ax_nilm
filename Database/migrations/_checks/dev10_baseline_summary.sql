-- dev10 가구별 cluster_label + 실측 일별 kWh baseline (ch01 = 메인 분전반)
-- 더미 historical generator 의 base 값 도출용
\echo '== dev10 households cluster_label =='
SELECT household_id, cluster_label, dr_enrolled, aggregator_id
  FROM households
 WHERE household_id IN ('H011','H015','H016','H017','H033','H039','H049','H054','H063','H067')
 ORDER BY cluster_label, household_id;

\echo '== dev10 ch01 가구별 일별 kWh 평균 (shift 후 power_1min) =='
WITH daily AS (
    SELECT household_id,
           date_trunc('day', bucket_ts AT TIME ZONE 'Asia/Seoul') AS day_kst,
           SUM(energy_wh) / 1000.0 AS kwh
      FROM power_1min
     WHERE channel_num = 1
       AND household_id IN ('H011','H015','H016','H017','H033','H039','H049','H054','H063','H067')
     GROUP BY household_id, date_trunc('day', bucket_ts AT TIME ZONE 'Asia/Seoul')
)
SELECT household_id,
       count(*) AS days,
       round(avg(kwh)::numeric, 2) AS mean_kwh,
       round(min(kwh)::numeric, 2) AS min_kwh,
       round(max(kwh)::numeric, 2) AS max_kwh,
       round(stddev(kwh)::numeric, 2) AS std_kwh
  FROM daily
 GROUP BY household_id
 ORDER BY household_id;

\echo '== dev10 ch01 요일별 평균 (weekday_factor 도출용) =='
WITH daily AS (
    SELECT household_id,
           extract(dow FROM (bucket_ts AT TIME ZONE 'Asia/Seoul')) AS dow,
           date_trunc('day', bucket_ts AT TIME ZONE 'Asia/Seoul') AS day_kst,
           SUM(energy_wh) / 1000.0 AS kwh
      FROM power_1min
     WHERE channel_num = 1
     GROUP BY household_id, dow, date_trunc('day', bucket_ts AT TIME ZONE 'Asia/Seoul')
)
SELECT dow::int AS dow_0sun,
       count(DISTINCT household_id || '_' || day_kst::text) AS samples,
       round(avg(kwh)::numeric, 2) AS mean_kwh
  FROM daily
 GROUP BY dow
 ORDER BY dow;
