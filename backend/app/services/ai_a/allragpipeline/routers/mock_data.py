from app.services.ai_a.allragpipeline.common.schemas import RAGResponse, Citation

# =========================================================
# Department-Based Mock Data (Standard 5-Dept Model)
# =========================================================
# DEPT_MGT: 경영지원본부
# DEPT_CORP_TAX: 법인세무본부
# DEPT_PROP_TAX: 재산세무본부
# DEPT_AUDIT: 회계감사본부
# DEPT_CONSULT: 컨설팅본부
# =========================================================

# 1. Graph Mock Data
MOCK_GRAPH_BY_DEPT = {
    "DEPT_MGT": {
        "nodes": [
            {"id": "doc_mgt_1", "label": "2024 인사규정.pdf", "group": "document", "value": 20},
            {"id": "doc_mgt_2", "label": "비품관리대장.xlsx", "group": "document", "value": 15},
            {"id": "c_hr", "label": "인사관리", "group": "concept", "value": 10},
            {"id": "c_ad", "label": "총무", "group": "concept", "value": 8}
        ],
        "links": [
            {"source": "c_hr", "target": "doc_mgt_1", "value": 5},
            {"source": "c_ad", "target": "doc_mgt_2", "value": 3}
        ]
    },
    "DEPT_CORP_TAX": {
        "nodes": [
            {"id": "doc_ctx_1", "label": "A사 법인세 신고서.pdf", "group": "document", "value": 20},
            {"id": "doc_ctx_2", "label": "분기 재무제표.xlsx", "group": "document", "value": 15},
            {"id": "c_vat", "label": "부가세", "group": "concept", "value": 10},
            {"id": "c_fin", "label": "재무분석", "group": "concept", "value": 8}
        ],
        "links": [
            {"source": "c_vat", "target": "doc_ctx_1", "value": 5},
            {"source": "c_fin", "target": "doc_ctx_2", "value": 3}
        ]
    },
    "DEPT_PROP_TAX": {
        "nodes": [
            {"id": "doc_ptx_1", "label": "상속세 신고가이드.pdf", "group": "document", "value": 20},
            {"id": "doc_ptx_2", "label": "양도세 계산기.xls", "group": "document", "value": 15},
            {"id": "c_inh", "label": "상속/증여", "group": "concept", "value": 10},
            {"id": "c_est", "label": "부동산", "group": "concept", "value": 8}
        ],
        "links": [
            {"source": "c_inh", "target": "doc_ptx_1", "value": 5},
            {"source": "c_est", "target": "doc_ptx_2", "value": 3}
        ]
    },
    "DEPT_AUDIT": {
        "nodes": [
            {"id": "doc_aud_1", "label": "S전자 감사보고서_Final.pdf", "group": "document", "value": 30},
            {"id": "doc_aud_2", "label": "내부회계 관리규정.docx", "group": "document", "value": 25},
            {"id": "c_risk", "label": "Risk Assessment", "group": "concept", "value": 15},
            {"id": "c_ctrl", "label": "Internal Control", "group": "concept", "value": 12}
        ],
        "links": [
            {"source": "c_risk", "target": "doc_aud_1", "value": 8},
            {"source": "c_ctrl", "target": "doc_aud_2", "value": 6}
        ]
    },
    "DEPT_CONSULT": {
        "nodes": [
            {"id": "doc_con_1", "label": "M&A Valuation Report.pdf", "group": "document", "value": 25},
            {"id": "doc_con_2", "label": "시장조사 보고서.pptx", "group": "document", "value": 20},
            {"id": "c_val", "label": "Valuation", "group": "concept", "value": 10},
            {"id": "c_mkt", "label": "Market Research", "group": "concept", "value": 8}
        ],
        "links": [
            {"source": "c_val", "target": "doc_con_1", "value": 5},
            {"source": "c_mkt", "target": "doc_con_2", "value": 4}
        ]
    }
}

# Fallback for Admin or Unknown
MOCK_GRAPH_GLOBAL = {
    "nodes": [
        {"id": "root", "label": "OmniHub Global View", "group": "concept", "value": 50},
        {"id": "dept_1", "label": "경영지원", "group": "concept", "value": 20},
        {"id": "dept_2", "label": "세무본부", "group": "concept", "value": 20},
        {"id": "dept_3", "label": "감사본부", "group": "concept", "value": 20}
    ],
    "links": [
        {"source": "root", "target": "dept_1", "value": 10},
        {"source": "root", "target": "dept_2", "value": 10},
        {"source": "root", "target": "dept_3", "value": 10}
    ]
}

# 2. RAG Mock Data (Simple One)
MOCK_RAG_RESPONSE = RAGResponse(
    answer="[Mock] This specific document is only visible to your department. The system verified your access level before retrieving this information.",
    citations=[
        Citation(
            idx=1,
            doc_id="doc_secure_1",
            title="Department Confidential.pdf",
            snippet="This content is restricted to authorized personnel only...",
            page=12,
            source_link="https://drive.google.com/file/d/xxxx",
            relevance=0.98
        )
    ],
    meta={
        "model_version": "mock-rbac-v1",
        "latency_ms": 95,
        "retrieved_count": 1
    },
    follow_up=["Show related confidential docs", "Check access logs"]
)

# 3. Tree Mock Data
MOCK_TREE_BY_DEPT = {
    "DEPT_MGT": {
        "current_path": "/",
        "folders": [{"name": "인사팀", "path": "/인사팀", "type": "folder"}, {"name": "총무팀", "path": "/총무팀", "type": "folder"}],
        "files": [{"name": "사규.pdf", "doc_id": "mgt_1", "type": "file"}]
    },
    "DEPT_AUDIT": {
        "current_path": "/",
        "folders": [{"name": "감사1팀", "path": "/감사1팀", "type": "folder"}, {"name": "감사2팀", "path": "/감사2팀", "type": "folder"}],
        "files": [{"name": "감사계획서.docx", "doc_id": "aud_1", "type": "file"}]
    }
    # ... omit others for brevity, will fallback safely
}

MOCK_TREE_GLOBAL = {
    "current_path": "/",
    "folders": [
        {"name": "경영지원본부", "path": "/MGT", "type": "folder"},
        {"name": "회계감사본부", "path": "/AUDIT", "type": "folder"},
        {"name": "법인세무본부", "path": "/CORP", "type": "folder"}
    ],
    "files": []
}

# 4. Doc Card Mock Data
MOCK_DOC_CARD = {
    "doc_id": "mock_id",
    "title": "Mock Document (RBAC Protected)",
    "folder_path": "/Internal/Secure",
    "modified_time": "2024-02-04T10:00:00Z",
    "source_link": "https://google.com",
    "review_status": "approved",
    "card": {
        "l1": "This document is secured by RBAC.",
        "l2": "Only users with matching department ID can view deep analysis.",
        "l3": "Access is logged and monitored by the Security Dashboard."
    },
    "policy": {
        "security_level": "high",
        "ssot_level": "gold"
    },
    "concepts": ["RBAC", "Security", "Mock"],
    "evidence": []
}

MOCK_GRAPH_EXPAND = {
    "nodes": [
        {"id": "sub_1", "label": "확장 노드 1", "group": "concept", "value": 10},
        {"id": "doc_sub_1", "label": "상세 보고서.docx", "group": "document", "value": 5}
    ],
    "links": [
        {"source": "sub_1", "target": "doc_sub_1", "value": 3}
    ]
}
