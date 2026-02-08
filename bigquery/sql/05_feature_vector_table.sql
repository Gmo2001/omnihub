CREATE OR REPLACE TABLE `${PROJECT_ID}.${DS_FEATURES}.${TB_VECTOR}` AS
SELECT
  u.userId,
  u.windowStart,
  
  -- 1. 다운로드 관련 Feature
  u.maxDownloadsPerSec5m,
  u.userDownloads5m,
  u.denyCount5m,
  u.totalCount5m,
  
  -- 2. 부서 통계 Join (다운로드 기준)
  -- JOIN 실패 시 0으로 채움
  COALESCE(d.deptMeanDownloads5m, 0) AS deptMeanDownloads5m,
  COALESCE(d.deptStdDownloads5m, 0) AS deptStdDownloads5m,
  
  -- 3. Z-Score (Anomaly Key Feature)
  COALESCE(
    SAFE_DIVIDE(u.userDownloads5m - d.deptMeanDownloads5m, NULLIF(d.deptStdDownloads5m, 0)),
    0
  ) AS z,
  
  -- 4. Positive Z-Score (Risk Add Score용)
  GREATEST(
    0,
    COALESCE(
      SAFE_DIVIDE(u.userDownloads5m - d.deptMeanDownloads5m, NULLIF(d.deptStdDownloads5m, 0)),
      0
    )
  ) AS zPos,

  -- 5. Deny Ratio (Rule Base용)
  COALESCE(
    SAFE_DIVIDE(u.denyCount5m, NULLIF(u.totalCount5m, 0)),
    0
  ) AS denyRatio5m

FROM `${PROJECT_ID}.${DS_FEATURES}.${TB_USER_5M}` u
LEFT JOIN `${PROJECT_ID}.${DS_FEATURES}.${TB_DEPT_STATS}` d
  ON u.userDeptId = d.userDeptId;