from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


@dataclass(frozen=True)
class EventRiskParts:
    base: float       # 0~100 (권장: 0~60)
    add: float        # 0~100 (권장: 0~40)
    mult: float       # 가중치
    event_risk: int   # 0~100 정수


def compute_base_from_recon_error(
    recon_error: float,
    train_mean: float,
    train_std: float,
    p95_threshold: float,
) -> float:
    """
    최종 스펙:
    (A) reconError >= p95Threshold -> base 최소 60
    (B) 그 외 -> z-score 기반 base = min(50, |z| * 10)

    p98Threshold는 입력에 없으므로 사용하지 않음.
    """
    eps = 1e-9
    z = abs((recon_error - train_mean) / max(train_std, eps))
    base = min(50.0, z * 10.0)

    if p95_threshold > 0 and recon_error >= p95_threshold:
        base = max(base, 60.0)

    return clamp(base, 0.0, 100.0)


def compute_add_from_metadata(metadata: Dict[str, Any]) -> float:
    """
    최종 스펙:
    - add1 = min(20, userDownloads5m / 10)
    - add2 = min(20, zPos * 5)
    - add = add1 + add2
    """
    user_downloads_5m = _safe_float(metadata.get("userDownloads5m"), 0.0)
    z_pos = _safe_float(metadata.get("zPos"), 0.0)

    add1 = min(20.0, max(0.0, user_downloads_5m) / 10.0)
    add2 = min(20.0, max(0.0, z_pos) * 5.0)

    return clamp(add1 + add2, 0.0, 100.0)


def compute_mult_from_event_type(event_type: str) -> float:
    key = (event_type or "").strip().upper()
    mult_map = {
        "MODEL_ANOMALY": 1.0,
        "MASS_DOWNLOAD": 1.2,
        "DENY_ACCESS": 1.5,
        "NORMAL_ACTIVITY": 0.5,
    }
    return float(mult_map.get(key, 1.0))


def build_event_risk_parts(
    recon_error: float,
    train_mean: float,
    train_std: float,
    p95_threshold: float,
    metadata: Dict[str, Any],
    event_type: str,
) -> EventRiskParts:
    base = compute_base_from_recon_error(
        recon_error=recon_error,
        train_mean=train_mean,
        train_std=train_std,
        p95_threshold=p95_threshold,
    )
    add = compute_add_from_metadata(metadata)
    mult = compute_mult_from_event_type(event_type)

    raw = (base + add) * mult
    raw = clamp(raw, 0.0, 100.0)
    event_risk = int(round(raw))

    return EventRiskParts(base=base, add=add, mult=mult, event_risk=event_risk)


def build_event_risk_inputs(
    recon_error: float,
    event_type: str,
    metadata: Dict[str, Any],
    train_mean: float = 0.0,
    train_std: float = 1.0,
    p95_threshold: float = 0.0,
) -> Dict[str, Any]:
    parts = build_event_risk_parts(
        recon_error=recon_error,
        train_mean=train_mean,
        train_std=train_std,
        p95_threshold=p95_threshold,
        metadata=metadata,
        event_type=event_type,
    )
    # dataclass -> dict conversion
    from dataclasses import asdict
    res = asdict(parts)
    # risk_engine에서 "eventRisk" 키를 씁니다. (EventRiskParts 필드명이 event_risk라서 변환 필요)
    # 하지만 dataclass 필드명이 event_risk이므로 snake_case입니다.
    # risk_engine.py를 보니 event_inputs.get("eventRisk")를 찾습니다.
    # 따라서 키를 맞춰줘야 합니다.
    res["eventRisk"] = parts.event_risk 
    return res
