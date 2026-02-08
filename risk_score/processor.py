from __future__ import annotations
import hashlib

from typing import Any, Dict, Optional

from stores import Stores
from risk_logic import build_event_risk_inputs
from risk_engine import RiskScoreEngine
from utils import json_dumps_stable, utc_stamp


def _normalize_event_type(v: Any) -> str:
    # 문자열뿐 아니라 숫자형도 안전하게 문자열로 변환하여 처리
    if v is None:
        return "MODEL_ANOMALY"
    s = str(v).strip().upper()
    if not s:
        return "MODEL_ANOMALY"
    return s


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _pick_ts(payload: Dict[str, Any]) -> str:
    v = payload.get("createdAt")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return utc_stamp()


def _idempotency_key(bucket: str, name: str, generation: Optional[str]) -> str:
    # Firestore 문서 ID에는 '/'가 들어가면 안 됨 → 해시로 안전하게
    raw = f"gcs:{bucket}:{name}:{generation or ''}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"idem_{digest}"


def process_gcs_output_json(
    *,
    stores: Stores,
    bucket: str,
    name: str,
    generation: Optional[str] = None,
) -> Dict[str, Any]:
    # outputs/*.json만 처리
    if not (name.startswith("outputs/") and name.endswith(".json")):
        return {"ignored": True, "reason": "not outputs/*.json"}

    idem_key = _idempotency_key(bucket, name, generation)
    if not stores.claim_idempotency(idem_key):
        return {"skipped": True, "reason": "duplicate", "idempotencyKey": idem_key}

    payload = stores.download_json_from_gcs(bucket=bucket, name=name, generation=generation)

    trace_id = str(payload.get("traceId") or "").strip() or f"trace_missing_{name.replace('/', '_')}"
    user_id = str(payload.get("userId") or "").strip() or "user_unknown"

    event_type = _normalize_event_type(payload.get("eventType"))
    recon_error = _safe_float(payload.get("reconError"), 0.0)

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    created_at = _pick_ts(payload)

    prev_doc = stores.get_user_latest(user_id) or {}
    prev_score = _safe_float(prev_doc.get("riskScore"), 0.0)
    prev_state = str(prev_doc.get("defconMode") or "safe")

    inputs = build_event_risk_inputs(
        recon_error=recon_error,
        event_type=event_type,
        metadata=metadata,
        train_mean=_safe_float(payload.get("trainMean"), 0.0),
        train_std=_safe_float(payload.get("trainStd"), 1.0),
        p95_threshold=_safe_float(payload.get("p95Threshold"), 0.0),
    )

    engine = RiskScoreEngine()
    out = engine.process_event(prev_score=prev_score, event_inputs=inputs, prev_state=prev_state)

    # Firestore: user 최신 상태 upsert
    # Firestore: user 최신 상태 upsert (는 하지 않음, 껍데기 유지)
    
    # 상세 데이터 (History용 - 모든 정보 포함)
    detail_payload = {
        "userId": user_id,
        "traceId": trace_id,
        "eventType": event_type,
        "reconError": recon_error,
        "eventRisk": int(out["eventRisk"]),
        "riskScore": int(out["riskScore"]),
        "defconMode": out["defconMode"],
        "stateChanged": bool(out["stateChanged"]),
        "metadata": metadata,
        
        # 모델 기준값 추가 (분석용)
        "trainMean": _safe_float(payload.get("trainMean"), 0.0),
        "trainStd": _safe_float(payload.get("trainStd"), 0.0),
        "p95Threshold": _safe_float(payload.get("p95Threshold"), 0.0),
        
        "gcs": {"bucket": bucket, "name": name, "generation": generation},
        "lastEventAt": created_at,
        "updatedAt": utc_stamp(),
    }
    
    # [NEW] 서브 컬렉션(history)에만 추가 (상위 문서는 필드 없이 껍데기로 존재)
    stores.add_user_history(user_id, detail_payload)

    # BigQuery: 현재 테이블 스키마에 맞춰 이벤트 1건 append
    # (필수 REQUIRED 컬럼을 모두 채움)
    bq_row = {
        "ingestedAt": utc_stamp(),                 # 테이블 REQUIRED
        "traceId": trace_id,                       # 테이블 REQUIRED
        "userId": user_id,                         # 테이블 REQUIRED

        # 테이블에 actionType REQUIRED인데, 오토인코더 JSON엔 없으니
        # eventType을 actionType으로 매핑해서라도 채워야 insert 가능
        "actionType": event_type,                  # REQUIRED 충족

        # 오토인코더가 주는 baseline 값들 (없으면 0.0으로 채움)
        "trainMean": _safe_float(payload.get("trainMean"), 0.0),
        "trainStd": _safe_float(payload.get("trainStd"), 0.0),
        "p95Threshold": _safe_float(payload.get("p95Threshold"), 0.0),

        # 오토인코더 핵심 값
        "reconError": recon_error,
        "anomalyScore": _safe_float(payload.get("anomalyScore"), 0.0),

        # 우리 최종 risk score(누적) 결과
        "riskScore": float(out["riskScore"]),

        # 상태 필드명도 테이블에 맞춤
        "state": out["defconMode"],
        "stateChanged": bool(out["stateChanged"]),

        # GCS 정보
        "gcsBucket": bucket,
        "gcsObject": name,
        "gcsGeneration": str(generation or ""),

        # metadata는 STRING 컬럼이라 JSON 문자열로 저장
        "metadata": json_dumps_stable(metadata),
    }

    insert_id = f"{trace_id}:{generation or ''}"
    stores.append_bq_event(bq_row, insert_id=insert_id)

    return {
        "ok": True,
        "traceId": trace_id,
        "userId": user_id,
        "eventType": event_type,
        "idempotencyKey": idem_key,
        "risk": out,
    }
