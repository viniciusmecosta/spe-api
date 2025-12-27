from sqlalchemy.orm import Session
from app.repositories.adjustment_repository import adjustment_repository
from app.schemas.adjustment import AdjustmentRequestCreate
from app.domain.models.adjustment import AdjustmentRequest

class AdjustmentService:
    def create_request(self, db: Session, user_id: int, request_in: AdjustmentRequestCreate) -> AdjustmentRequest:
        # Aqui poderiam entrar validações de negócio, como verificar se já existe solicitação para a data
        # ou se a data é futura (se não for permitido).
        return adjustment_repository.create(db, user_id, request_in)

adjustment_service = AdjustmentService()