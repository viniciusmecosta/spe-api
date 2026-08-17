import pytest
from app.shared.hashid_service import HashidService


def test_hashid_encode_decode():
    service = HashidService(salt="test_salt", min_length=6)

    encoded = service.encode(12345)
    assert isinstance(encoded, str)
    assert len(encoded) >= 6

    decoded = service.decode(encoded)
    assert decoded == 12345


def test_hashid_decode_invalid():
    service = HashidService(salt="test_salt", min_length=6)

    decoded = service.decode("invalid_hash")
    assert decoded is None


def test_hashid_encode_negative_raises_value_error():
    service = HashidService(salt="test_salt", min_length=6)
    with pytest.raises(ValueError):
        service.encode(-1)
