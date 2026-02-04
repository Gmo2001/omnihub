import os
import json
import logging
from typing import Dict, Any, List

from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import SecurityLevel, SSoTLevel

# Logger
logger = logging.getLogger("PolicyClassifier")
logger.setLevel(logging.INFO)

# --- Rule Engine ---
class PolicyEngine:
    def __init__(self, rules_path: str):
        # 만약 rule 파일이 없으면 기본값 사용 or 에러
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
        else:
            logger.warning(f"Rules file not found at {rules_path}. Using empty rules.")
            self.rules = {}
            
    def evaluate(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """프로필을 입력받아 보안/SSOT 등급 결정"""
        
        # 기본값 (Safety Default)
        result = {
            "security_level": SecurityLevel.HIGH.value,
            "ssot_level": SSoTLevel.SILVER.value,
            "matched_rules": []
        }
        
        folder_path = profile.get("folder_path", "/") or "/"
        title = profile.get("title", "")
        perms = profile.get("permissions_summary", {})
        
        matched_results = [] # (priority, security, ssot, rule_info)
        
        # 1. Folder Rules (Priority 100)
        for rule in self.rules.get("folder_rules", []):
            if rule["pattern"] in folder_path:
                matched_results.append({
                    "priority": 100,
                    "security": rule["security"],
                    "ssot": rule["ssot"],
                    "reason": f"Folder Match: {rule['pattern']}"
                })
        
        # 2. Keyword Rules (Priority 50)
        for rule in self.rules.get("keyword_rules", []):
            if rule["keyword"] in title:
                matched_results.append({
                    "priority": 50,
                    "security": rule["security"],
                    "ssot": rule["ssot"],
                    "reason": f"Keyword Match: {rule['keyword']}"
                })
                
        # 3. Decision Logic
        if matched_results:
            matched_results.sort(key=lambda x: x["priority"], reverse=True)
            top_match = matched_results[0]
            
            result["security_level"] = SecurityLevel.normalize(top_match["security"]).value
            result["ssot_level"] = SSoTLevel.normalize(top_match["ssot"]).value
            
            for m in matched_results:
                result["matched_rules"].append(m["reason"])
        
        # 4. Permission Adjustment
        if perms.get("anyone_can_read") is True:
            current_sec = result["security_level"]
            if current_sec == SecurityLevel.HIGH.value:
                result["security_level"] = SecurityLevel.MEDIUM.value
                result["matched_rules"].append("Downgraded by Owner Permission (Anyone Can Read)")

        return result

# --- Main Processor ---
class PolicyClassifier:
    def __init__(self):
        self.db = get_firestore_client()
        self.tenant_id = getattr(settings, "TENANT_ID", "default_tenant")
        self.engagement_id = getattr(settings, "ENGAGEMENT_ID", "default_engagement")
        self.policy_version = getattr(settings, "POLICY_RULE_VERSION", "v1")
        
        # Rule File Path (backend/rules/...)
        # settings.BASE_DIR 활용 가능
        # 여기서는 상대 경로 가정 (app/services/ai_a/rules를 찾거나, 프로젝트 루트의 rules 찾기)
        # 보통 프로젝트 루트의 app/rag/rules/policy_rules.v1.json
        self.rules_file = os.path.join("app", "rag", "rules", f"policy_rules.{self.policy_version}.json")
        self.engine = PolicyEngine(self.rules_file)

    def process_single_document(self, doc_id: str):
        """Orchestrator 호출 포인트"""
        
        # 1. Profile 조회
        doc_ref = self.db.collection("profiles").document(doc_id).get()
        if not doc_ref.exists:
            logger.warning(f"SKIP Policy: Profile not found for {doc_id}")
            return
            
        doc_data = doc_ref.to_dict()
        
        if not doc_data.get("active"):
            logger.info(f"SKIP Policy: Document {doc_id} is not active")
            return

        logger.info(f"🛡️ [Policy] 분류 시작: {doc_id}")
        
        # 2. 룰 평가
        eval_result = self.engine.evaluate(doc_data)
        
        # 3. 저장 데이터 구성
        policy_data = {
            "doc_id": doc_id,
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            "doc_content_hash": doc_data.get("doc_content_hash"),
            "security_level": eval_result["security_level"],
            "ssot_level": eval_result["ssot_level"],
            "matched_rules": eval_result["matched_rules"],
            "rule_version": self.policy_version,
            "classified_at": firestore.SERVER_TIMESTAMP
        }
        
        batch = self.db.batch()
        
        # policies/{doc_id}
        batch.set(self.db.collection("policies").document(doc_id), policy_data, merge=True)
        
        # documents/{doc_id} (Serving)
        batch.set(self.db.collection("documents").document(doc_id), {
            "security_level": eval_result["security_level"],
            "ssot_level": eval_result["ssot_level"]
        }, merge=True)
        
        # profiles/{doc_id} (Flag Off)
        batch.set(self.db.collection("profiles").document(doc_id), {
            "process_flags": {"policy": False}
        }, merge=True)

        batch.commit()
        logger.info(f"✅ [Policy] 분류 완료: {eval_result['security_level']} / {eval_result['ssot_level']}")
