from enum import Enum

class SecurityLevel(Enum):
    LOW = "L1"
    MEDIUM = "L2"
    HIGH = "L3"
    CRITICAL = "L4" # Optional

    @classmethod
    def normalize(cls, val):
        if not val: return cls.HIGH
        upper = val.upper()
        if upper in ["L1", "LOW"]: return cls.LOW
        if upper in ["L2", "MEDIUM"]: return cls.MEDIUM
        if upper in ["L3", "HIGH"]: return cls.HIGH
        if upper in ["L4", "CRITICAL"]: return cls.CRITICAL
        return cls.HIGH

class SSoTLevel(Enum):
    BRONZE = "Draft"
    SILVER = "Verified"
    GOLD = "Official"

    @classmethod
    def normalize(cls, val):
        if not val: return cls.BRONZE
        # Mapping logic (Example)
        upper = str(val).upper()
        if "DRAFT" in upper or "BRONZE" in upper: return cls.BRONZE
        if "VERIF" in upper or "SILVER" in upper: return cls.SILVER
        if "OFFICIAL" in upper or "GOLD" in upper: return cls.GOLD
        return cls.BRONZE

class ReviewStatus(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    
    @classmethod
    def normalize(cls, val):
        if not val: return cls.PENDING
        try:
            return cls(val)
        except ValueError:
            return cls.PENDING
