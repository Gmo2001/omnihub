class VectorSchema:
    """
    Standard Namespaces for Vector Search Restricts
    """
    TENANT_ID = "tenant_id"
    ENGAGEMENT_ID = "engagement_id"
    DOC_ID = "doc_id"
    SECURITY_LEVEL = "security_level"
    REVIEW_STATUS = "review_status"
    
    # Optional
    CONTENT_HASH = "content_hash"
    CHUNK_POLICY = "chunk_policy_version"
    EMBED_MODEL = "embedding_model_version"

    @classmethod
    def get_mandatory_keys(cls):
        return [cls.TENANT_ID, cls.ENGAGEMENT_ID, cls.DOC_ID, cls.SECURITY_LEVEL, cls.REVIEW_STATUS]
