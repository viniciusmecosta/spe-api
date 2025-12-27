from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SPE - Sistema de Ponto Eletrônico"
    API_V1_STR: str = "/api/v1"
    TIMEZONE: str = "America/Fortaleza"
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./spe.db"

    class Config:
        case_sensitive = True

settings = Settings()