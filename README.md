# SPE — Sistema de Ponto Eletrônico

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/) [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2-D71F00)](https://www.sqlalchemy.org/) [![Pydantic](https://img.shields.io/badge/Pydantic-2-E92063)](https://docs.pydantic.dev/) [![Alembic](https://img.shields.io/badge/Alembic-migrações-6BA81E)](https://alembic.sqlalchemy.org/)

[![Granian](https://img.shields.io/badge/Granian-ASGI-5A4FCF)](https://github.com/emmett-framework/granian) [![APScheduler](https://img.shields.io/badge/APScheduler-rotinas-4B8BBE)](https://apscheduler.readthedocs.io/) [![JWT](https://img.shields.io/badge/JWT-autenticação-000000?logo=jsonwebtokens)](https://jwt.io/) [![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) [![uv](https://img.shields.io/badge/uv-dependências-DE5FE9)](https://docs.astral.sh/uv/) [![pytest](https://img.shields.io/badge/pytest-testes-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)

API de controle de ponto para registrar jornadas, tratar ajustes, apurar horas e fechar a folha. Gestores administram colaboradores e relatórios; mantenedores configuram integrações e operações. As regras ficam nos serviços, com persistência PostgreSQL e tarefas duráveis no banco.

A API integra aplicativos clientes, equipamentos biométricos e firmware OTA, impressoras ESC/POS, SMTP e Telegram. Usa NTP para horário confiável e gera comprovantes PDF com QR Code e relatórios PDF e Excel.

## Executar

Com Python 3.12+, uv e PostgreSQL disponíveis, copie [`.env.example`](.env.example) para `.env` e configure as variáveis descritas em [README.env.md](README.env.md). Depois execute:

```bash
uv sync --locked --no-build
uv run alembic upgrade head
uv run python -m app.initial_data
uv run granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app
```

A documentação interativa está em `/docs`, o esquema OpenAPI em `/api/v1/openapi.json` e as verificações em `/api/v1/health` e `/api/v1/ready`. Para iniciar o PostgreSQL e a API com Compose, use `docker compose up --build` após configurar o ambiente.

## Autenticação e API

O login usa `POST /api/v1/auth/login`; chamadas protegidas enviam o access token como Bearer. O refresh rotativo usa `POST /api/v1/auth/refresh`, e o logout revoga a sessão. Quando exigida por gestor ou mantenedor, a troca de senha bloqueia os demais recursos até `POST /api/v1/auth/password` ser concluído. [Detalhes de sessões e implantação](AUTH_SESSIONS.md).

As principais áreas da API são:

| Área | Recursos |
| --- | --- |
| Pessoas e jornada | Usuários, empresas, expedientes, feriados e dispositivos. |
| Ponto | Marcações, ajustes, apurações diárias, anomalias e comprovantes. |
| Gestão | Folha, relatórios, painéis e registros de auditoria. |
| Operação | Tarefas, backups, impressoras, biometria, firmware e notificações. |

Consulte os caminhos, permissões e formatos atuais em `/docs`. Contratos antigos preservados aparecem como depreciados. A API limita requisições por origem e responde `429` com `Retry-After` quando necessário. [Configuração e operação](README.operacao.md).

## Verificação

```bash
uv run pytest
uv run ruff check app scripts
```

Os testes de integração PostgreSQL usam `SPE_TEST_DATABASE_URL` apontando para um servidor descartável; o fixture cria e remove bancos temporários. Os comandos de backup e restauração estão em [scripts/README.md](scripts/README.md).
