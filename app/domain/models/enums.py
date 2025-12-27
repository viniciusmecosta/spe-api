import enum


class UserRole(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"


class RecordType(str, enum.Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class AdjustmentType(str, enum.Enum):
    MISSING_ENTRY = "MISSING_ENTRY"
    MISSING_EXIT = "MISSING_EXIT"
    BOTH = "BOTH"


class AdjustmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
