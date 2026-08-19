from hashids import Hashids

from app.core.config import settings


class HashidService:
    def __init__(self, salt: str = settings.SECRET_KEY, min_length: int = 6):
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        self._hashids = Hashids(salt=salt, min_length=min_length, alphabet=alphabet)

    def encode(self, number: int) -> str:
        if number < 0:
            raise ValueError("O número a ser codificado deve ser positivo.")
        return self._hashids.encode(number)

    def decode(self, hash_str: str) -> int | None:
        hash_str = hash_str.upper()
        decoded = self._hashids.decode(hash_str)
        if not decoded:
            return None
        return decoded[0]


hashid_service = HashidService()
