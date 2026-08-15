from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cnpj = Column(String, unique=True, index=True, nullable=False)
    address = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    logo_path = Column(String, nullable=True)
    auto_print_receipt = Column(Boolean, default=False, nullable=False)
    default_printer_id = Column(Integer, ForeignKey("printers.id"), nullable=True)

    printers = relationship("Printer", back_populates="company", foreign_keys="Printer.company_id")
    default_printer = relationship("Printer", foreign_keys=[default_printer_id])
