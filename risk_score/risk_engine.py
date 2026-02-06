from __future__ import annotations

from dataclasses import dataclass


def clamp_int(x: float, lo: int = 0, hi: int = 100) -> int:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return int(round(x))


@dataclass(frozen=True)
class RiskResult:
    riskScore: int
    eventRisk: int
    defconMode: str
    stateChanged: bool


class RiskScoreEngine:
    """
    - eventRisk: 이번 이벤트의 위험도(0~100)
    - riskScore: 누적 위험도(0~100)
    - defconMode: safe/watch/alert
    """

    def process_event(self, *, prev_score: float, event_inputs: dict, prev_state: str) -> dict:
        event_risk = clamp_int(event_inputs["eventRisk"])

        # 누적 점수: 간단 누적(필요하면 decay를 여기에 넣어도 됨)
        new_score = clamp_int(prev_score + event_risk)

        # 상태 결정
        if new_score >= 70:
            mode = "alert"
        elif new_score >= 40:
            mode = "watch"
        else:
            mode = "safe"

        state_changed = (mode != (prev_state or "safe").lower())

        return {
            "riskScore": new_score,
            "eventRisk": event_risk,
            "defconMode": mode,
            "stateChanged": state_changed,
        }
