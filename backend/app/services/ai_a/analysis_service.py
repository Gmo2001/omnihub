from app.schemas.ai_request import AIAnalysisRequest
from app.models.ai_insight import AIInsightSchema
from app.core.gcp_clients import db
import datetime
from app.core.logger import log_system_event

async def analyze_file_content(request: AIAnalysisRequest):
    """
    [Phase 3] AI 분석 서비스 Entry Point
    - Input: AIAnalysisRequest (GCS URI + Context)
    - Output: None (내부에서 ai_insights 컬렉션에 저장)
    """
    print(f"🤖 [AI Service] Analyzing file: {request.file_name} (GCS: {request.gcs_uri})...")
    
    # [Verification Log] AI Handoff 패키지 내용 확인
    print(f"📦 [AI Handoff Check] GCS: {request.gcs_uri}, Path: {request.full_path}, Owner: {request.owners}")
    
    # === Mock Logic (실제 AI 연동은 여기 아래에 구현) ===
    # 1. GCS URI가 있으면 -> Document AI / Gemini Flash 호출
    # 2. extracted_text가 있으면 -> LLM 호출
    
    # 3. 결과 저장 (Separation of Concerns)
    # [Mod] 사용자 요청으로 심화 분석 필드 사용 중지 (Schema 주석 처리됨)
    # 추후 스키마가 확정되면 다시 활성화할 예정
    insight = AIInsightSchema(
        file_id=request.file_id
    )
    
    # 3-1. Insight 저장
    try:
        # file_id를 문서 ID로 사용하면 1:1 관계, add() 쓰면 1:N 관계
        # 여기서는 관리 편의상 file_id를 Key로 사용하여 1:1 유지 (덮어쓰기)
        # [Fix] CamelCase Enforcement
        db.collection('ai_insights').document(request.file_id).set(insight.dict(by_alias=True))
        
        # [Phase 4] System Log: AI Analysis Completed
        log_system_event(
            event_type="AI_ANALYSIS_COMPLETED",
            component="AnalysisService",
            payload=insight.dict(by_alias=True)
        )
        print(f"✅ [AI Service] Insight Saved: {request.file_id}")
        
        # 3-2. 원본 상태 업데이트 (완료)
        # [Fix] CamelCase Key
        db.collection('files').document(request.file_id).update({"aiStatus": "completed"})
        
    except Exception as e:
        log_system_event(
            event_type="AI_ANALYSIS_FAILED",
            component="AnalysisService",
            payload={"file_id": request.file_id, "error": str(e)},
            severity="ERROR"
        )
        print(f"❌ [AI Service] Save Failed: {e}")
        # [Fix] CamelCase Key
        db.collection('files').document(request.file_id).update({"aiStatus": "failed"})

    return insight.dict()
