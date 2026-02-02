from enum import Enum

class SecurityLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @classmethod
    def normalize(cls, value: str) -> "SecurityLevel":
        if not value:
            return cls.LOW
        v = value.upper().strip()
        if v in ["HIGH", "L3", "SECRET", "TOP SCERET"]: 
            return cls.HIGH
        if v in ["MEDIUM", "L2", "CONFIDENTIAL", "INTERNAL"]: 
            return cls.MEDIUM
        if v in ["LOW", "L1", "PUBLIC", "UNCLASSIFIED"]: 
            return cls.LOW
        return cls.LOW

class SSoTLevel(str, Enum):
    GOLD = "Gold"
    SILVER = "Silver"

    @classmethod
    def normalize(cls, value: str) -> "SSoTLevel":
        if not value:
            return cls.SILVER
        v = value.upper().strip()
        if v in ["GOLD", "PRIMARY", "MASTER"]: 
            return cls.GOLD
        return cls.SILVER

class ReviewStatus(str, Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"

    @classmethod
    def normalize(cls, value: str) -> "ReviewStatus":
        if not value:
            return cls.PENDING
        v = value.upper().strip()
        if v == "APPROVED": 
            return cls.APPROVED
        if v == "REJECTED": 
            return cls.REJECTED
        # DRAFT, PENDING, or others -> PENDING
        return cls.PENDING
