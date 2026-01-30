import os
import json
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv
from google.cloud import firestore
from common.enums import SecurityLevel, SSoTLevel

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    POLICY_VERSION = os.getenv("POLICY_RULE_VERSION", "v1")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    RULES_FILE = f"rules/policy_rules.{POLICY_VERSION}.json"

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not os.path.exists(cls.RULES_FILE):
             raise ValueError(f"Rule File Not Found: {cls.RULES_FILE}")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("PolicyClassifier")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Rule Engine ---
class PolicyEngine:
    def __init__(self, rules_path: str):
        with open(rules_path, 'r', encoding='utf-8') as f:
            self.rules = json.load(f)
            
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
        # 가장 높은 Priority의 룰을 채택하거나, 보안은 가장 엄격한 것(High > Medium > Low)을 선택
        # 여기서는 "가장 명시적인 매칭(Priority)"을 우선시하는 로직으로 구현
        
        if matched_results:
            # Priority 내림차순 정렬
            matched_results.sort(key=lambda x: x["priority"], reverse=True)
            top_match = matched_results[0]
            
            result["security_level"] = SecurityLevel.normalize(top_match["security"]).value
            result["ssot_level"] = SSoTLevel.normalize(top_match["ssot"]).value
            
            for m in matched_results:
                result["matched_rules"].append(m["reason"])
        
        # 4. Permission Adjustment (보정)
        # 만약 Anyone Can Read인데 High Security라면? -> 모순이므로 조정하거나 Alert.
        # 규칙: Anyone Can Read이면 보안등급을 최대 Medium으로 낮춘다 (이미 공개된 것이므로)
        if perms.get("anyone_can_read") is True:
            current_sec = result["security_level"]
            if current_sec == SecurityLevel.HIGH.value:
                result["security_level"] = SecurityLevel.MEDIUM.value
                result["matched_rules"].append("Downgraded by Owner Permission (Anyone Can Read)")

        return result

# --- Main Processor ---
class PolicyClassifier:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.engine = PolicyEngine(Config.RULES_FILE)

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        doc_data = doc_snapshot.to_dict() # profiles/{doc_id}
        
        # 필요한 정보가 없으면 스킵? build_profile이 선행되어야 함
        if not doc_data.get("active"):
            return

        logger.info(f"Classifying {doc_id} ({doc_data.get('title')})...")
        
        # 룰 평가
        eval_result = self.engine.evaluate(doc_data)
        
        # 저장 데이터 구성
        policy_data = {
            "doc_id": doc_id,
            "tenant_id": Config.TENANT_ID,
            "engagement_id": Config.ENGAGEMENT_ID,
            "doc_content_hash": doc_data.get("doc_content_hash"),
            "security_level": eval_result["security_level"],
            "ssot_level": eval_result["ssot_level"],
            "matched_rules": eval_result["matched_rules"],
            "rule_version": Config.POLICY_VERSION,
            "classified_at": firestore.SERVER_TIMESTAMP
        }
        
        # Firestore Update (Batch)
        batch = self.db.batch()
        
        # 1. policies/{doc_id}
        pol_ref = self.db.collection("policies").document(doc_id)
        batch.set(pol_ref, policy_data, merge=True)
        
        # 2. documents/{doc_id} (Serving용)
        doc_ref = self.db.collection("documents").document(doc_id)
        batch.set(doc_ref, {
            "security_level": eval_result["security_level"],
            "ssot_level": eval_result["ssot_level"]
        }, merge=True)
        
        # 3. profiles/{doc_id} (Flag Update)
        # Policy 처리가 끝났으므로 process_flags.policy = False로 끌 수 있음 (선택사항)
        # 운영상 무한 루프 방지를 위해 끄는 것이 좋음
        prof_ref = self.db.collection("profiles").document(doc_id)
        batch.set(prof_ref, {"process_flags": {"policy": False}}, merge=True)

        batch.commit()
        logger.info(f" -> Level: {eval_result['security_level']} / {eval_result['ssot_level']}")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Policy Classification 작업 시작...")
        
        # profiles 컬렉션 조회
        # 전체 재처리 or process_flags.policy == True 인 것만 조회
        # 여기선 간단히 profiles 전체 active=True
        docs = self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).stream()
        
        count = 0
        for doc in docs:
            # process_flags.policy == True 인지 확인 (클라이언트 사이드 필터링)
            d = doc.to_dict()
            flags = d.get("process_flags", {})
            if flags.get("policy") is False:
                 continue
                 
            self.process_document(doc)
            count += 1
            
        logger.info(f"작업 완료. 총 {count}개 분류됨.")

if __name__ == "__main__":
    classifier = PolicyClassifier()
    classifier.run_batch()
