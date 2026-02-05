CREATE OR REPLACE VIEW `${PROJECT_ID}.${DS_CLEAN}.${TB_CLEAN_AUDIT}` AS
SELECT
  timestamp AS eventTs,
  document_id AS documentId,
  SAFE_CAST(JSON_VALUE(data, "$.actionType") AS INT64) AS actionType,
  CASE SAFE_CAST(JSON_VALUE(data, "$.actionType") AS INT64)
    WHEN 0 THEN 'VIEW'
    WHEN 1 THEN 'DOWNLOAD'
    WHEN 2 THEN 'MOVE'
    WHEN 3 THEN 'APPROVE'
    WHEN 4 THEN 'DENIED'
    WHEN 5 THEN 'LOGIN'
    WHEN 6 THEN 'LOGOUT'
    WHEN 7 THEN 'DELETE'
    WHEN 8 THEN 'TRASH'
    WHEN 9 THEN 'CREATE'
    WHEN 10 THEN 'UPDATE'
    ELSE 'UNKNOWN'
  END AS actionTypeName,
  CASE
    WHEN STARTS_WITH(JSON_VALUE(data, "$.fileId"), "fil_") THEN JSON_VALUE(data, "$.fileId")
    ELSE CONCAT("fil_", JSON_VALUE(data, "$.fileId"))
  END AS fileId,
  CASE
    WHEN STARTS_WITH(JSON_VALUE(data, "$.userId"), "usr_") THEN JSON_VALUE(data, "$.userId")
    ELSE CONCAT("usr_", JSON_VALUE(data, "$.userId"))
  END AS userId,
  -- 부서 정보가 NULL이면 기본값 부여
  COALESCE(JSON_VALUE(data, "$.userDepartmentId"), 'DEPT_UNKNOWN') AS userDeptId
FROM `${PROJECT_ID}.${DS_RAW_AUDIT}.${TB_AUDIT_SOURCE}`;