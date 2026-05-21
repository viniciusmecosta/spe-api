from sqlalchemy import Column, Integer, String

from app.database.base import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cnpj = Column(String, unique=True, index=True, nullable=False)
    address = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    logo_path = Column(String, nullable=True)
