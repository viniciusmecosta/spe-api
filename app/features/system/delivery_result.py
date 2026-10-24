from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    detail: str = ""
    retry_after: int = 0
    recipients: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return self.status == "SUCCESS"
