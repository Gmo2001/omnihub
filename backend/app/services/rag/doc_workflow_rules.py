from typing import Dict, Any, Optional
from app.common.enums import ReviewStatus, SecurityLevel

class DocWorkflowRules:
    @classmethod
    def apply(cls, new_status: str) -> Dict[str, Any]:
        """
        문서 상태 변경에 따른 파생 필드 업데이트 계산.
        
        Rules:
        - APPROVED: active=True, graph_visible=True, searchable=True
        - REJECTED / ARCHIVED: active=False, graph_visible=False, searchable=False
        - PENDING: active=True (목록 노출), graph_visible=False, searchable=False
        """
        status = ReviewStatus.normalize(new_status).value
        updates = {
            "review_status": status
        }
        
        if status == ReviewStatus.APPROVED.value:
            updates["active"] = True
            updates["graph_visible"] = True
            updates["searchable"] = True
            
        elif status in [ReviewStatus.REJECTED.value, ReviewStatus.ARCHIVED.value]:
            updates["active"] = False
            updates["graph_visible"] = False
            updates["searchable"] = False
            
        elif status == ReviewStatus.PENDING.value:
            # 검토 중: 목록엔 보이지만 그래프/검색엔 노출 안됨
            updates["active"] = True
            updates["graph_visible"] = False
            updates["searchable"] = False
            
        return updates
