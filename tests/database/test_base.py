from sqlalchemy import Column, Integer

from app.database.base import Base


class SampleModel(Base):
    id = Column(Integer, primary_key=True)


def test_base_tablename():
    assert SampleModel.__tablename__ == "samplemodel"
