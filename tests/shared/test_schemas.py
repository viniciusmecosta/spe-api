from app.shared.schemas import MessageResponse, SuccessResponse, DataResponse, PaginatedResponse


def test_shared_schemas():
    msg = MessageResponse(detail="test")
    assert msg.detail == "test"

    succ = SuccessResponse(message="ok")
    assert succ.status == "success"
    assert succ.message == "ok"

    data = DataResponse[str](data="payload")
    assert data.status == "success"
    assert data.data == "payload"

    paginated = PaginatedResponse[int](items=[1, 2, 3], total=3, page=1, size=10, pages=1)
    assert paginated.items == [1, 2, 3]
    assert paginated.total == 3
    assert paginated.page == 1
    assert paginated.size == 10
    assert paginated.pages == 1
