from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# Firestore 'files' 컬렉션 구조를 json 규격으로 정의
class FileSchema(BaseModel):
    # ==========================================
    # [Google Drive Sync] 담당자: Infra/Backend (Sync Service) 🤖
    # - 구글 드라이브에서 직접 가져오는 원본 데이터 영역입니다.
    # - Sync Service 외에는 이 값을 임의로 수정하지 마세요.
    # ==========================================
    file_id: str          # Google Drive Original ID
    name: str             # 파일명
    mime_type: str        # 파일 타입 (application/pdf, folder 등)
    parents: List[str] = [] # 상위 폴더 ID 리스트 (트리 구조)
    
    webview_link: Optional[str] = None     # 드라이브 열기 링크
    thumbnail_link: Optional[str] = None   # 썸네일 URL
    icon_link: Optional[str] = None        # 아이콘 URL
    owners: List[str] = []                 # 소유자 정보 (이름 등)
    
    is_folder: bool = False                # 폴더 여부
    trashed: bool = False                  # 휴지통 여부
    
    # [Phase 3 Expansion] AI 분석 및 추적을 위한 추가 메타데이터
    gcs_uri: Optional[str] = None          # GCS 원본 파일 경로 (gs://...)
    last_modified_by: Optional[str] = None # 마지막 수정자 (협업 맥락 파악)
    full_path: Optional[str] = None        # 실제 드라이브 경로 (예: /Shared/2024/Project)
    
    # ==========================================
    # [AI Analysis Result] 담당자: AI/ML Engineer 🧠
    # - 텍스트 추출 후 LLM이 분석하여 채워넣는 메타데이터입니다=> 아직 어떤 메타 데이터 넣어야할지는 미정!!
    # - Ingestion Service 및 AI Pipeline에서 업데이트합니다.
    # ==========================================
    # [Status for Phase 3]
    ai_status: str = Field(default="ready")  # ready, processing, completed, failed

    # ==========================================

    # ==========================================
    # [System Lifecycle] 담당자: Backend Core ⚙️
    # - 시스템 상태 및 타임스탬프 관리 영역입니다.
    # ==========================================
    status: str = Field(default="pending") # pending(대기) -> processing(분석중) -> approved(완료) or deleted
    
    created_at: datetime = Field(default_factory=datetime.now) # (Drive) 파일 생성일
    updated_at: datetime = Field(default_factory=datetime.now) # (Drive) 파일 수정일
    last_synced_at: datetime = Field(default_factory=datetime.now) # (System) 마지막 동기화 시간

# API 응답용 모델 (ID 포함)
class FileResponse(FileSchema):
    pass # sync_service.py에서 문서를 찾기위한 주소와 조회한 데이터 내용안의 