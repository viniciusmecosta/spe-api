# SPE — Sistema de Ponto Eletrônico

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/) [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2-D71F00)](https://www.sqlalchemy.org/) [![Pydantic](https://img.shields.io/badge/Pydantic-2-E92063)](https://docs.pydantic.dev/) [![Alembic](https://img.shields.io/badge/Alembic-migrações-6BA81E)](https://alembic.sqlalchemy.org/)

[![Granian](https://img.shields.io/badge/Granian-ASGI-5A4FCF)](https://github.com/emmett-framework/granian) [![APScheduler](https://img.shields.io/badge/APScheduler-rotinas-4B8BBE)](https://apscheduler.readthedocs.io/) [![JWT](https://img.shields.io/badge/JWT-autenticação-000000?logo=jsonwebtokens)](https://jwt.io/) [![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) [![uv](https://img.shields.io/badge/uv-dependências-DE5FE9)](https://docs.astral.sh/uv/) [![pytest](https://img.shields.io/badge/pytest-testes-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)

API de controle de ponto eletrônico para registrar jornadas, tratar ajustes, apurar horas e fechar a folha mensal. Gestores administram colaboradores e relatórios; mantenedores configuram integrações e operações. As regras de negócio residem nos serviços, com persistência PostgreSQL e fila durável de tarefas no banco.

## Execução

Com Python 3.12+, `uv` e PostgreSQL disponíveis, copie [`.env.example`](.env.example) para `.env`, ajuste as variáveis de ambiente e execute:

```bash
uv sync --locked --no-build
uv run alembic upgrade head
uv run python -m app.initial_data
uv run granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app
```

A documentação interativa fica em `/docs`, o contrato OpenAPI em `/api/v1/openapi.json` e as sondas de saúde e prontidão em `/api/v1/health` e `/api/v1/ready`. Para subir via Docker Compose:

```bash
docker compose up --build
```

## Autenticação, Sessões e Redefinição Obrigatória de Senha

- `POST /api/v1/auth/login`: autentica credenciais e retorna `access_token`, `expires_in`, `refresh_token`, `refresh_expires_in` e `password_change_required`.
- `POST /api/v1/auth/refresh`: rotaciona o refresh token com detecção de reutilização (RFC 9700 §4.14), revogando toda a família em caso de replay.
- `POST /api/v1/auth/logout`: revoga a família da sessão ativa e retorna `204`.
- `POST /api/v1/auth/password`: redefine a senha do usuário autenticado, limpa `password_change_required`, incrementa `auth_version` e emite nova sessão.
- Quando `password_change_required=true`, o login emite apenas um token restrito (`purpose=password_change`), bloqueando as demais rotas até a troca de senha.

## Principais Recursos da API

| Área | Recursos |
| --- | --- |
| Pessoas e jornada | Usuários (`/api/v1/users`), empresa (`/api/v1/companies`), expedientes em minutos diários (`/api/v1/schedules`), feriados (`/api/v1/holidays`) e dispositivos (`/api/v1/devices`). |
| Ponto | Marcações unificadas (`/api/v1/time-records`), ajustes e revisões (`/api/v1/adjustments`), apurações diárias (`/api/v1/daily-summaries`), espelhos (`/api/v1/timesheets`) e comprovantes PDF. |
| Gestão | Transições de folha (`/api/v1/payroll/{year}/{month}/transitions`), relatórios e exportações (`/api/v1/reports`) e auditoria (`/api/v1/audit-logs`). |
| Operação | Jobs manuais (`/api/v1/operations/jobs`), backups criptografados, impressoras (`/api/v1/printers`), biometria e firmware OTA (`/api/v1/firmware`). |

Todos os documentos gerados pela aplicação (Excel, espelho de ponto PDF, comprovante PDF e exportação operacional JSON) incluem nos metadados um hash SHA-256 determinístico de autenticidade calculado a partir dos registros do banco.

## Operação, Limites de Requisição e Backups

- **Rate limiting em memória**: aplica limites por IP em janelas móveis de 1s (`RATE_LIMIT_REQUESTS_PER_SECOND=30`), 60s (`RATE_LIMIT_REQUESTS_PER_MINUTE=600`) e rotas de autenticação (`RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE=60`), respondendo `429` com `Retry-After`. Configure `TRUSTED_PROXY_CIDRS` quando operar atrás de proxy reverso.
- **Backup e restauração PostgreSQL**:
  - `make dump`: gera pacote criptografado `spe.zip.enc` com manifesto SHA-256 e contagens por tabela.
  - `make restore`: valida manifesto e restaura `spe.zip.enc`.
  - `make db-restore-test`: valida restauração em banco temporário sem afetar o banco principal.

## Testes e Qualidade

```bash
uv run pytest
uv run ruff check app scripts
uv run mypy app/
```

Para executar a suíte completa incluindo testes de integração e migrações Alembic em PostgreSQL, defina `SPE_TEST_DATABASE_URL` apontando para uma instância PostgreSQL de testes.
