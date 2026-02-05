CREATE OR REPLACE TABLE `${PROJECT_ID}.${DS_FEATURES}.${TB_VECTOR}` AS
SELECT
  u.userId,
  u.windowStart,
  u.maxDownloadsPerSec5m,
  u.userDownloads5m,
  -- JOIN 실패 시 0으로 채움
  COALESCE(d.deptMeanDownloads5m, 0) AS deptMeanDownloads5m,
  COALESCE(d.deptStdDownloads5m, 0) AS deptStdDownloads5m,
  COALESCE(
    SAFE_DIVIDE(u.userDownloads5m - d.deptMeanDownloads5m, NULLIF(d.deptStdDownloads5m, 0)),
    0
  ) AS z,
  GREATEST(
    0,
    COALESCE(
      SAFE_DIVIDE(u.userDownloads5m - d.deptMeanDownloads5m, NULLIF(d.deptStdDownloads5m, 0)),
      0
    )
  ) AS zPos
FROM `${PROJECT_ID}.${DS_FEATURES}.${TB_USER_5M}` u
LEFT JOIN `${PROJECT_ID}.${DS_FEATURES}.${TB_DEPT_STATS}` d
  ON u.userDeptId = d.userDeptId;