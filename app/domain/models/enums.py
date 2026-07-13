import enum

class UserRole(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    MAINTAINER = "MAINTAINER"

class RecordType(str, enum.Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"

class AdjustmentType(str, enum.Enum):
    FORGOT_PUNCH = "FORGOT_PUNCH"
    PUNCH_NOT_COUNTED = "PUNCH_NOT_COUNTED"
    DELETE_PUNCH = "DELETE_PUNCH"
    WAIVER = "WAIVER"
    OTHER = "OTHER"

class AdjustmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class DeviceKeyType(str, enum.Enum):
    DEVICE = "DEVICE"
    CONSUMER = "CONSUMER"
