# Configuração, variáveis do `.env.example` e rate limit

[![Pydantic Settings](https://img.shields.io/badge/Pydantic_Settings-2.15%2B-E92063)](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) [![Starlette](https://img.shields.io/badge/Starlette-1.6%2B-009688)](https://www.starlette.io/) [![limits](https://img.shields.io/badge/limits-5.8%2B-4B8BBE)](https://limits.readthedocs.io/) [![asyncpg](https://img.shields.io/badge/asyncpg-0.29%2B-336791)](https://magicstack.github.io/asyncpg/) [![Pillow](https://img.shields.io/badge/Pillow-12.3%2B-3776AB)](https://python-pillow.org/)

Referência de todas as variáveis de ambiente do [`.env.example`](../.env.example), funcionamento do middleware de rate limit por IP, configuração de proxy reverso e limites de upload.

## Bibliotecas utilizadas

- `pydantic-settings` e `python-dotenv`: leitura e validação tipada das variáveis do `.env` em [`app/core/config.py`](../app/core/config.py).
- `starlette`: middleware de limite de tamanho do body HTTP (`RequestBodyLimitMiddleware`) e base dos middlewares ASGI de rate limit e log de requisições (`X-Request-ID`).
- `ipaddress` (biblioteca padrão): validação das redes CIDR em `TRUSTED_PROXY_CIDRS` para extrair o IP real do cliente no header `X-Forwarded-For`.
- `pillow`: verificação de largura, altura e total de pixels antes de abrir imagens enviadas no upload.

## Rate limit por IP e rotas de autenticação

O [`RateLimitMiddleware`](../app/middleware/rate_limit.py) controla a quantidade de requisições por IP usando janelas deslizantes em memória:

- Janela de 1 segundo (`RATE_LIMIT_REQUESTS_PER_SECOND`): barra rajadas acima do limite por segundo (padrão `30` req/s por IP).
- Janela de 60 segundos (`RATE_LIMIT_REQUESTS_PER_MINUTE`): limita o volume total por minuto (padrão `600` req/min por IP).
- Janela de autenticação (`RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE`): limite próprio para `/api/v1/auth/*` e `/api/v1/devices/verify-manager` (padrão `60` req/min por IP).

Os endpoints `/`, `/api/v1/health` e `/api/v1/ready` ficam fora da contagem para não bloquear healthchecks.

Quando o limite estoura, o middleware responde `429 Too Many Requests` com o header `Retry-After` (segundos até liberar) e body no padrão RFC 9457 Problem Details (`type: "https://api.spe.com/erros/limite-de-requisicoes"`, `code: "RATE_LIMIT_EXCEEDED"`).

### Uso atrás de proxy reverso (`TRUSTED_PROXY_CIDRS`)

O middleware só lê o header `X-Forwarded-For` se o IP da conexão direta (`request.client.host`) estiver dentro de uma das faixas configuradas em `TRUSTED_PROXY_CIDRS`. Se `TRUSTED_PROXY_CIDRS` estiver vazio (`[]`), o `X-Forwarded-For` é ignorado para evitar que clientes forjem o próprio IP. Quando preenchido, o middleware lê a lista do `X-Forwarded-For` da direita para a esquerda e pega o primeiro IP que não pertence aos proxies confiáveis.

## Limites de upload e validação de arquivos

Os uploads passam por duas checagens:

1. No middleware ASGI (`RequestBodyLimitMiddleware`), que recusa requisições com body acima de `UPLOAD_REQUEST_MAX_BYTES` (`33554432` bytes / 32 MiB por padrão) antes de chegar ao controller.
2. No storage ([`app/shared/upload_storage.py`](../app/shared/upload_storage.py)), que confere assinatura binária (magic bytes), extensão e limite por tipo de arquivo:
   - Logo da empresa: até `UPLOAD_LOGO_MAX_BYTES` (5 MiB), máximo de `UPLOAD_LOGO_MAX_DIMENSION` (4096 px) de lado e `UPLOAD_LOGO_MAX_PIXELS` (16 megapixels).
   - Anexos de ajuste (atestados e comprovantes): até `UPLOAD_ATTACHMENT_MAX_BYTES` (10 MiB).
   - Binários de firmware OTA (`.bin`): até `UPLOAD_FIRMWARE_MAX_BYTES` (16 MiB).
   - Relatórios de folha legada (`.xlsx` e `.pdf`): até `UPLOAD_LEGACY_REPORT_MAX_BYTES` (25 MiB).

## Variáveis do `.env.example`

### Aplicação e ambiente

| Variável | Exemplo / Padrão | Descrição |
| --- | --- | --- |
| `PROJECT_NAME` | `"SPE - Sistema de Ponto Eletrônico"` | Nome da API exibido na rota raiz, relatórios e OpenAPI. |
| `APP_VERSION` | `"1.4.2"` | Versão retornada em `/api/v1/health` e no OpenAPI. |
| `ENVIRONMENT` | `"PROD"` | Ambiente de execução (`DEV`, `TEST` ou `PROD`). |
| `TIMEZONE` | `"America/Fortaleza"` | Fuso horário usado na apuração de ponto, agendador cron e registros de batida. |
| `UPLOAD_DIR` | `"uploads"` | Pasta local onde ficam salvos anexos, logos, relatórios fechados e firmwares. |
| `BACKEND_CORS_ORIGINS` | `'["*"]'` | Lista JSON de origens liberadas no CORS. |

### PostgreSQL e pool de conexões

| Variável | Exemplo / Padrão | Descrição |
| --- | --- | --- |
| `POSTGRES_DB` | `"spe_db"` | Nome do banco PostgreSQL usado pelos scripts e pelo Docker Compose. |
| `POSTGRES_USER` | `"spe_user"` | Usuário do PostgreSQL. |
| `POSTGRES_PASSWORD` | `"your_postgres_password"` | Senha do usuário do PostgreSQL. |
| `POSTGRES_HOST` | `"localhost"` | Host do PostgreSQL. |
| `POSTGRES_PORT` | `5432` | Porta do PostgreSQL. |
| `SQLALCHEMY_DATABASE_URI` | `"postgresql+asyncpg://..."` | URI de conexão usada pelo SQLAlchemy assíncrono e pelo Alembic. |
| `DB_POOL_SIZE` | `5` | Quantidade de conexões mantidas no pool do SQLAlchemy. |
| `DB_MAX_OVERFLOW` | `5` | Conexões extras acima de `DB_POOL_SIZE` permitidas em pico. |
| `DB_POOL_TIMEOUT_SECONDS` | `15` | Tempo máximo de espera por uma conexão livre no pool. |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` | Timeout para abrir conexão com o PostgreSQL. |
| `DB_STATEMENT_TIMEOUT_MS` | `120000` | Tempo máximo de execução de uma query SQL (120s). |
| `DB_LOCK_TIMEOUT_MS` | `10000` | Tempo máximo esperando por lock de linha ou advisory lock (10s). |
| `DB_IDLE_TRANSACTION_TIMEOUT_MS` | `60000` | Tempo máximo que uma transação pode ficar aberta sem atividade (60s). |

### Autenticação, JWT e usuário inicial

| Variável | Exemplo / Padrão | Descrição |
| --- | --- | --- |
| `SECRET_KEY` | Obrigatória | Chave usada para assinar tokens JWT, gerar hashids de comprovantes e criptografar backups. |
| `ALGORITHM` | `"HS256"` | Algoritmo de assinatura do JWT. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Tempo de vida em minutos do access token normal. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Tempo de vida em dias de cada refresh token emitido. |
| `PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES` | `10` | Tempo de vida em minutos do token temporário emitido quando `password_change_required=true`. |
| `FIRST_SUPERUSER` | `""` | Username do mantenedor criado por `python -m app.initial_data`. |
| `FIRST_SUPERUSER_PASSWORD` | `""` | Senha inicial desse mantenedor. |

### E-mail (SMTP) e Telegram

| Variável | Exemplo / Padrão | Descrição |
| --- | --- | --- |
| `SMTP_HOST` | `"smtp.gmail.com"` | Host do servidor SMTP para envio dos relatórios diários. |
| `SMTP_PORT` | `587` | Porta SMTP (STARTTLS). |
| `SMTP_USER` | `""` | Usuário de autenticação no SMTP. |
| `SMTP_PASSWORD` | `""` | Senha ou senha de app do SMTP. |
| `EMAIL_FROM` | `""` | Endereço remetente dos e-mails enviados. |
| `TELEGRAM_BOT_TOKEN` | `""` | Token do bot do Telegram que envia alertas, logs e backups. |
| `TELEGRAM_CHAT_ID` | `""` | ID do chat ou grupo que recebe as mensagens no Telegram. |
| `TELEGRAM_MAX_MESSAGE_LENGTH` | `3900` | Limite de caracteres por mensagem antes de dividir o texto no envio ao Telegram. |

### Rotinas cron, fila de jobs e reprocessamento

| Variável | Exemplo / Padrão | Descrição |
| --- | --- | --- |
| `BACKGROUND_JOBS_ENABLED` | `true` | Liga ou desliga o worker que processa a tabela `background_jobs`. |
| `ROUTINE_LOG_RETENTION_DAYS` | `15` | Quantos dias os registros de `routine_logs` são mantidos antes da limpeza diária. |
| `DAILY_REPORT_HOUR` | `9` | Hora do dia (0 a 23) em que o relatório diário é enviado. |
| `HOURLY_BACKUP_START_HOUR` | `6` | Hora inicial da janela diária de backups automáticos. |
| `HOURLY_BACKUP_END_HOUR` | `19` | Hora final da janela diária de backups automáticos. |
| `REPROCESS_MAX_DAYS` | `3660` | Máximo de dias aceito em um pedido de reprocessamento de apurações. |
| `REPROCESS_MAX_ITEMS` | `100000` | Limite de combinações funcionário-dia em um único job de reprocessamento. |
| `REPROCESS_BATCH_SIZE` | `25` | Quantidade de dias processados por transação no reprocessamento. |

### Rate limit, proxy reverso e limites de upload

| Variável | Exemplo / Padrão | Descrição |
| --- | --- | --- |
| `TRUSTED_PROXY_CIDRS` | `[]` | Lista de CIDRs de proxies reversos confiáveis para leitura de `X-Forwarded-For`. |
| `RATE_LIMIT_ENABLED` | `true` | Ativa ou desativa o middleware de rate limit. |
| `RATE_LIMIT_REQUESTS_PER_SECOND` | `30` | Máximo de requisições por segundo por IP. |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `600` | Máximo de requisições por minuto por IP. |
| `RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE` | `60` | Máximo de requisições por minuto por IP nas rotas de login e autenticação. |
| `UPLOAD_REQUEST_MAX_BYTES` | `33554432` | Tamanho máximo do body HTTP aceito pela API (32 MiB). |
| `UPLOAD_LOGO_MAX_BYTES` | `5242880` | Tamanho máximo da imagem de logo da empresa (5 MiB). |
| `UPLOAD_ATTACHMENT_MAX_BYTES` | `10485760` | Tamanho máximo de anexos de ajuste (10 MiB). |
| `UPLOAD_FIRMWARE_MAX_BYTES` | `16777216` | Tamanho máximo de arquivos `.bin` de firmware OTA (16 MiB). |
| `UPLOAD_LEGACY_REPORT_MAX_BYTES` | `26214400` | Tamanho máximo de relatórios de folha legada (25 MiB). |
| `UPLOAD_LOGO_MAX_DIMENSION` | `4096` | Largura ou altura máxima em pixels da logo da empresa. |
| `UPLOAD_LOGO_MAX_PIXELS` | `16000000` | Total máximo de pixels (`largura * altura`) da logo da empresa. |
