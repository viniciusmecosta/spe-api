from pydantic import BaseModel, ConfigDict


class PrinterBase(BaseModel):
    name: str
    address: str
    status: bool = True
    paper_width: int = 80
    company_id: int


class PrinterCreate(PrinterBase):
    pass


class PrinterUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    status: bool | None = None
    paper_width: int | None = None
    company_id: int | None = None


class PrinterInDBBase(PrinterBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class Printer(PrinterInDBBase):
    pass


class PrinterResponse(Printer):
    pass
