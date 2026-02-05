CREATE OR REPLACE VIEW `${PROJECT_ID}.${DS_CLEAN}.${TB_CLEAN_SYSTEM}` AS
SELECT
  timestamp AS eventTs,
  jsonPayload.event_type AS eventType,
  jsonPayload.component AS component,
  jsonPayload.payload AS payload
FROM `${PROJECT_ID}.${DS_RAW_SYSTEM}.${TB_SYSTEM_WILDCARD}`
WHERE _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL ${N_DAYS} DAY));