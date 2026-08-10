from typing import Optional

from pydantic import BaseModel


class PrinterBase(BaseModel):
    name: str
    address: str
    status: bool = True
    paper_width: int = 80
    company_id: int


class PrinterCreate(PrinterBase):
    pass


class PrinterUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    status: Optional[bool] = None
    paper_width: Optional[int] = None
    company_id: Optional[int] = None


class PrinterInDBBase(PrinterBase):
    id: int

    class Config:
        from_attributes = True


class Printer(PrinterInDBBase):
    pass
