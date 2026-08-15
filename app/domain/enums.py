import enum
from datetime import date, datetime


class DayOfWeek(int, enum.Enum):
    SEGUNDA = 0
    TERCA = 1
    QUARTA = 2
    QUINTA = 3
    SEXTA = 4
    SABADO = 5
    DOMINGO = 6

    @property
    def nome(self) -> str:
        names = {
            0: "Segunda-feira",
            1: "Terça-feira",
            2: "Quarta-feira",
            3: "Quinta-feira",
            4: "Sexta-feira",
            5: "Sábado",
            6: "Domingo",
        }
        return names[self.value]

    @property
    def abreviado(self) -> str:
        names = {
            0: "Segunda",
            1: "Terça",
            2: "Quarta",
            3: "Quinta",
            4: "Sexta",
            5: "Sábado",
            6: "Domingo",
        }
        return names[self.value]

    @property
    def sigla(self) -> str:
        names = {
            0: "Seg",
            1: "Ter",
            2: "Qua",
            3: "Qui",
            4: "Sex",
            5: "Sáb",
            6: "Dom",
        }
        return names[self.value]

    @classmethod
    def from_date(cls, dt: date | datetime) -> "DayOfWeek":
        return cls(dt.weekday())


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
    EXTRA_TIME = "EXTRA_TIME"
    OTHER = "OTHER"


class AdjustmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DeviceKeyType(str, enum.Enum):
    DEVICE = "DEVICE"
    CONSUMER = "CONSUMER"
