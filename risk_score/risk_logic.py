from __future__ import annotations

from typing import Any, Dict


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def build_event_risk_inputs(*, recon_error: float, event_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    - recon_error 기반 기본 위험 + 행동/상황 기반 추가 위험을 간단히 합산해서 eventRisk로 만든다.
    - event_type은 문자열로 들어오는 걸 기준(upper normalize는 processor에서 처리).
    """
    # base: recon_error를 0~100 스케일로 단순 변환(필요하면 trainMean/std/p95로 정교화 가능)
    base = _clamp(recon_error * 100.0, 0.0, 100.0)

    # add: metadata 기반 추가 위험(예: userDownloads5m, zPos)
    add = 0.0
    ud = metadata.get("userDownloads5m")
    if isinstance(ud, (int, float)):
        add += _clamp(float(ud) * 2.0, 0.0, 30.0)

    z = metadata.get("zPos")
    if isinstance(z, (int, float)):
        add += _clamp(abs(float(z)) * 5.0, 0.0, 30.0)

    # mult: event_type 가중치(문자열)
    mult = 1.0
    if event_type in {"DENY_ACCESS"}:
        mult = 1.2
    elif event_type in {"MODEL_ANOMALY"}:
        mult = 1.3
    elif event_type in {"MASS_DOWNLOAD"}:
        mult = 1.6
    elif event_type in {"SUSPICIOUS_MOVE"}:
        mult = 1.4

    event_risk = _clamp((base + add) * mult, 0.0, 100.0)

    return {
        "eventRisk": event_risk,
        "base": base,
        "add": add,
        "mult": mult,
    }
