# SPE - Sistema de Ponto Eletrônico

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.141%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Starlette](https://img.shields.io/badge/Starlette-1.6%2B-009688)](https://www.starlette.io/) [![Granian](https://img.shields.io/badge/Granian-2.8%2B-5A4FCF)](https://github.com/emmett-framework/granian) [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/) [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)](https://www.sqlalchemy.org/) [![asyncpg](https://img.shields.io/badge/asyncpg-0.29%2B-336791)](https://magicstack.github.io/asyncpg/) [![Alembic](https://img.shields.io/badge/Alembic-1.18%2B-6BA81E)](https://alembic.sqlalchemy.org/)

[![Pydantic](https://img.shields.io/badge/Pydantic-2.13%2B-E92063)](https://docs.pydantic.dev/) [![PyJWT](https://img.shields.io/badge/PyJWT-2.13%2B-000000?logo=jsonwebtokens)](https://pyjwt.readthedocs.io/) [![bcrypt](https://img.shields.io/badge/bcrypt-5.0%2B-4B8BBE)](https://pypi.org/project/bcrypt/) [![Cryptography](https://img.shields.io/badge/Cryptography-45.0%2B-3776AB)](https://cryptography.io/) [![APScheduler](https://img.shields.io/badge/APScheduler-3.11%2B-4B8BBE)](https://apscheduler.readthedocs.io/) [![OpenPyXL](https://img.shields.io/badge/OpenPyXL-3.1%2B-217346)](https://openpyxl.readthedocs.io/) [![ReportLab](https://img.shields.io/badge/ReportLab-5.0%2B-B30B00)](https://www.reportlab.com/) [![HTTPX](https://img.shields.io/badge/HTTPX-0.28%2B-2C5BB4)](https://www.python-httpx.org/)

[![ESC/POS](https://img.shields.io/badge/python--escpos-3.1%2B-555555)](https://python-escpos.readthedocs.io/) [![ntplib](https://img.shields.io/badge/ntplib-0.4%2B-555555)](https://pypi.org/project/ntplib/) [![uv](https://img.shields.io/badge/uv-pacotes-DE5FE9)](https://docs.astral.sh/uv/) [![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) [![pytest](https://img.shields.io/badge/pytest-9.1%2B-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/) [![Ruff](https://img.shields.io/badge/Ruff-0.17.2-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/) [![mypy](https://img.shields.io/badge/mypy-2.3%2B-2A6DB2)](https://mypy-lang.org/)

API do Sistema de Ponto Eletrônico (SPE) em FastAPI e PostgreSQL. Recebe batidas de ponto pelo app e pelos coletores biométricos ESP32, calcula a apuração diária com base nos expedientes em minutos, controla solicitações de ajuste, fecha a folha mensal e gera os relatórios em Excel, PDF e JSON.

## Arquitetura e camadas da API

O código em `app/` é dividido por domínio em `app/features/` e segue separação estrita por camada:

- Controllers (`app/features/*/*_router.py`): recebem a requisição HTTP, validam os schemas de entrada, injetam o usuário ou coletor autenticado via `Depends` e repassam a chamada para o service. Nenhuma regra de negócio ou query SQL fica no controller.
- Services (`app/features/*/*_service.py`): executam as regras de negócio, cálculos de jornada, validações de permissão por escopo, fechamento de folha, geração de arquivos e gravação de logs em `audit_logs`.
- Repositories e Models (`app/features/*/*_repository.py`, `*_models.py` e `app/database/`): acesso a dados com `SQLAlchemy 2.0` assíncrono (`asyncpg`) e controle transacional via `UnitOfWork`. Operações sensíveis a concorrência usam `pg_advisory_xact_lock` (cadastro/edição de expedientes e fechamento de folha) e `SELECT ... FOR UPDATE` (rotação de refresh token e consumo da fila de jobs).
- Schemas (`app/features/*/*_schemas.py`): contratos Pydantic v2 de entrada e saída.
- Horário do servidor (`app/shared/trusted_time_service.py`): usa o relógio do PostgreSQL sincronizado com NTP (`ntplib`) no fuso configurado (`America/Fortaleza`), ignorando o horário local do aparelho do usuário no registro do ponto.
- Tratamento de erros (`app/core/exceptions.py`): respostas de erro padronizadas na RFC 9457 Problem Details (`type`, `title`, `status`, `detail`, `instance`) com `X-Request-ID` em todas as chamadas.

## Funcionamento dos módulos

### 1. Usuários, expedientes em minutos e auditoria

O cadastro de funcionários, gestores (`MANAGER`) e mantenedores (`MAINTAINER`) fica em `/api/v1/users`. Os expedientes (`user_work_schedule_configs`) são definidos por período de vigência (`valid_from` até `valid_until`) e dia da semana, salvando a carga diária em minutos inteiros (`daily_minutes`, de 0 a 1440).

Quando um expediente é criado, editado ou removido em lote (`/api/v1/schedules/bulk`), o módulo [`schedule_audit.py`](app/features/users/schedule_audit.py) salva no log de auditoria um resumo compactado (`schedule_change_summary`) que agrupa funcionários e dias com a mesma carga horária.

### 2. Registro de ponto, coletores ESP32 e impressoras térmicas

As batidas entram por dois caminhos:

- Pelo aplicativo (`/api/v1/time-records`), onde o funcionário bate o próprio ponto e o gestor pode registrar batidas manuais justificadas para a equipe.
- Pelos coletores biométricos (`/api/v1/devices/punch`), autenticados com o header `X-Device-API-Key`. Ao receber a batida do sensor, a API grava o ponto, envia o comprovante para a impressora térmica ESC/POS na rede (`python-escpos`) e libera a segunda via em PDF e QR Code por `short_id` (`hashids` + `reportlab` + `qrcode`).

### 3. Apuração diária, ajustes e fechamento de folha

Qualquer alteração em batidas, expedientes, ajustes ou feriados recalcula o resumo diário (`daily_summaries`) do funcionário na data alterada:

- O [`TimeCalculationService`](app/shared/time_calculation_service.py) cruza os pares de entrada e saída (`ENTRY`/`EXIT`) com o expediente ativo na data, aplica a tolerância da empresa e calcula saldo do dia, faltas, atrasos, batidas ímpares e horas excedentes.
- Os pedidos de ajuste com anexo passam por `/api/v1/adjustments`. Gestores aprovam, rejeitam ou lançam abonos (`/api/v1/adjustments/admin/waive`), disparando o recálculo do dia.
- No fechamento mensal (`POST /api/v1/payroll/{year}/{month}/transitions`), o service valida se há pendências, gera e congela a planilha `.xlsx` oficial do mês e trava edições naquele período. Para reabrir a folha, é obrigatório informar justificativa.

### 4. Verificação de documentos

Planilhas Excel, espelhos em PDF, comprovantes e exportações JSON recém-gerados recebem uma assinatura HMAC do conteúdo. Gestores podem enviar o arquivo a `/api/v1/documents/verify` para verificar se ele foi emitido por uma instalação com a mesma chave e permanece intacto. Arquivos antigos sem assinatura não são verificáveis por esse mecanismo. A verificação não substitui assinatura ICP-Brasil nem comprova a correção dos dados de origem.

## Bibliotecas utilizadas

| Biblioteca | Versão | Uso no projeto |
| --- | --- | --- |
| `fastapi` / `starlette` | `>=0.141.1` / `>=1.6.0` | Controllers HTTP, injeção de dependências, OpenAPI 3.1 e middlewares ASGI. |
| `granian` | `>=2.8.1` | Servidor ASGI em Rust para rodar a aplicação. |
| `sqlalchemy` / `asyncpg` | `>=2.0.52` / `>=0.29.0` | ORM assíncrono, pool de conexões e locks no PostgreSQL 17. |
| `alembic` | `>=1.18.5` | Migrações de schema e dados no PostgreSQL. |
| `pydantic` / `pydantic-settings` | `>=2.13.4` / `>=2.15.0` | Schemas de request/response e leitura tipada do `.env`. |
| `pyjwt` / `bcrypt` / `cryptography` | `>=2.13.0` / `>=5.0.0` / `>=45.0.0` | Tokens JWT, hash de senhas e chaves de coletores, e criptografia Fernet nos backups. |
| `apscheduler` / `ntplib` | `>=3.11.3` / `>=0.4.0` | Agendamento das rotinas cron e sincronização de horário via NTP. |
| `openpyxl` / `reportlab` / `pillow` / `qrcode` | `>=3.1.5` / `>=5.0.0` / `>=12.3.0` / `>=8.2` | Geração das planilhas `.xlsx`, espelhos e comprovantes `.pdf`, validação de imagens e QR Codes. |
| `python-escpos` / `hashids` | `>=3.1` / `>=1.3.1` | Impressão térmica em rede e identificadores curtos de comprovantes. |
| `httpx` / `limits` | `>=0.28.1` / `>=5.8` | Chamadas assíncronas para Telegram e BrasilAPI e controle de limites. |
| `pytest` / `ruff` / `mypy` | `>=9.1.1` / `0.17.2` / `>=2.3.0` | Testes automatizados com cobertura, lint e checagem estática de tipos. |

## Documentação detalhada (`docs/`)

- [`docs/autenticacao.md`](docs/autenticacao.md) - Login, JWT, rotação de refresh token, revogação de sessão e redefinição obrigatória de senha.
- [`docs/rotinas-e-cron.md`](docs/rotinas-e-cron.md) - Rotinas agendadas no APScheduler, fila `background_jobs`, envio de logs diários e alertas por e-mail e Telegram.
- [`docs/relatorios-e-excel.md`](docs/relatorios-e-excel.md) - Geração da planilha Excel, espelhos de ponto em PDF/ZIP, exportação operacional e hash `SHA-256`.
- [`docs/backup-e-restauracao.md`](docs/backup-e-restauracao.md) - Dump criptografado `spe.zip.enc`, manifesto de integridade, restore e teste em banco temporário.
- [`docs/configuracao-e-limites.md`](docs/configuracao-e-limites.md) - Variáveis do `.env.example`, proteção de requisições por IP, `TRUSTED_PROXY_CIDRS` e limites de upload.
- [`docs/endpoints.md`](docs/endpoints.md) - Lista completa de endpoints da API (`/api/v1`), métodos, parâmetros e permissões.

## Como rodar o projeto

Com Python 3.12+, `uv` e PostgreSQL 17 instalados, copie [`.env.example`](.env.example) para `.env`, ajuste as variáveis do banco e execute:

```bash
uv sync --locked --no-build
uv run alembic upgrade head
uv run python -m app.initial_data
uv run granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app
```

Pelo [`Makefile`](Makefile), os mesmos passos podem ser executados com `make setup`, `make upgrade`, `make seed` e `make run`.

Para subir tudo com Docker Compose:

```bash
docker compose up --build -d
```

Com a API rodando, o Swagger fica em `/docs`, o schema OpenAPI em `/api/v1/openapi.json` e os endpoints de healthcheck em `/api/v1/health` e `/api/v1/ready`.

## Testes e lint

```bash
uv run pytest
uv run ruff check app scripts
uv run mypy app/
```

Para rodar os testes de integração e testar todas as migrações Alembic no PostgreSQL, defina `SPE_TEST_DATABASE_URL` apontando para um banco de testes.
