CREATE OR REPLACE VIEW `${PROJECT_ID}.${DS_FEATURES}.${TB_USER_5M}` AS
-- 1. 5분 윈도우 계산 (전체 Action 대상)
WITH base AS (
  SELECT
    userId,
    userDeptId,
    eventTs,
    -- 5분 단위 Time Window 시작 시간 계산
    TIMESTAMP_SUB(
      TIMESTAMP_TRUNC(eventTs, MINUTE),
      INTERVAL MOD(EXTRACT(MINUTE FROM eventTs), 5) MINUTE
    ) AS windowStart,
    TIMESTAMP_TRUNC(eventTs, SECOND) AS secTs,
    actionType
  FROM `${PROJECT_ID}.${DS_CLEAN}.${TB_CLEAN_AUDIT}`
  -- WHERE actionType = ... (삭제: 전체 로그 사용)
),

-- 2. 초 단위 집계 (Burst 감지용)
sec_counts AS (
  SELECT
    userId,
    userDeptId,
    windowStart,
    secTs,
    -- 다운로드 수 (actionType=1)
    COUNTIF(actionType = 1) AS downloadsInSec,
    -- 차단 수 (actionType=4)
    COUNTIF(actionType = 4) AS deniesInSec,
    -- 전체 활동 수
    COUNT(*) AS totalInSec
  FROM base
  GROUP BY userId, userDeptId, windowStart, secTs
)

-- 3. 5분 단위 최종 집계
SELECT
  userId,
  userDeptId,
  windowStart,
  -- A. 최대 초당 다운로드 수 (Traffic Burst)
  MAX(downloadsInSec) AS maxDownloadsPerSec5m,
  
  -- B. 총 다운로드 수
  SUM(downloadsInSec) AS userDownloads5m,
  
  -- C. 총 차단 수
  SUM(deniesInSec) AS denyCount5m,
  
  -- D. 총 활동 수 (비율 계산용)
  SUM(totalInSec) AS totalCount5m
FROM sec_counts
GROUP BY userId, userDeptId, windowStart;