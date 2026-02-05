CREATE OR REPLACE TABLE `${PROJECT_ID}.${DS_FEATURES}.${TB_DEPT_STATS}` AS
WITH src AS (
  SELECT *
  FROM `${PROJECT_ID}.${DS_FEATURES}.${TB_USER_5M}`
  WHERE windowStart >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL ${N_DAYS} DAY)
)
SELECT
  userDeptId,
  AVG(userDownloads5m) AS deptMeanDownloads5m,
  -- 데이터가 1개일 때 계산 오류 방지
  COALESCE(STDDEV_SAMP(userDownloads5m), 0) AS deptStdDownloads5m,
  CURRENT_TIMESTAMP() AS computedAt
FROM src
GROUP BY userDeptId;