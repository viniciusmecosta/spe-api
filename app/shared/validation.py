from datetime import date
from typing import Annotated

from fastapi import HTTPException, Query
from pydantic import Field

Month = Annotated[int, Field(ge=1, le=12)]
Year = Annotated[int, Field(ge=2000, le=9998)]
BusinessDate = Annotated[date, Field(le=date(9998, 12, 31))]
PageOffset = Annotated[int, Query(ge=0, le=2**63 - 1)]
PageLimit = Annotated[int, Query(ge=1, le=1000)]


def validate_date_order(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise ValueError('A data inicial não pode ser maior que a data final.')


def validate_schedule_period(valid_from: date, valid_until: date) -> None:
    try:
        validate_date_order(valid_from, valid_until)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
