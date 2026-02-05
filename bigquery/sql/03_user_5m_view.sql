CREATE OR REPLACE VIEW `${PROJECT_ID}.${DS_FEATURES}.${TB_USER_5M}` AS
WITH base AS (
  SELECT
    userId,
    userDeptId,
    eventTs,
    TIMESTAMP_SUB(
      TIMESTAMP_TRUNC(eventTs, MINUTE),
      INTERVAL MOD(EXTRACT(MINUTE FROM eventTs), 5) MINUTE
    ) AS windowStart,
    TIMESTAMP_TRUNC(eventTs, SECOND) AS secTs
  FROM `${PROJECT_ID}.${DS_CLEAN}.${TB_CLEAN_AUDIT}`
  WHERE actionType = ${DOWNLOAD_ACTION_TYPE}
),
sec_counts AS (
  SELECT
    userId,
    userDeptId,
    windowStart,
    secTs,
    COUNT(*) AS downloadsInSec
  FROM base
  GROUP BY userId, userDeptId, windowStart, secTs
),
agg AS (
  SELECT
    userId,
    userDeptId,
    windowStart,
    SUM(downloadsInSec) AS userDownloads5m,
    MAX(downloadsInSec) AS maxDownloadsPerSec5m
  FROM sec_counts
  GROUP BY userId, userDeptId, windowStart
)
SELECT * FROM agg;