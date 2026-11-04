# Rotinas agendadas (cron), fila de jobs e notificações

[![APScheduler](https://img.shields.io/badge/APScheduler-3.11%2B-4B8BBE)](https://apscheduler.readthedocs.io/) [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)](https://www.sqlalchemy.org/) [![asyncpg](https://img.shields.io/badge/asyncpg-0.29%2B-336791)](https://magicstack.github.io/asyncpg/) [![HTTPX](https://img.shields.io/badge/HTTPX-0.28%2B-2C5BB4)](https://www.python-httpx.org/) [![ntplib](https://img.shields.io/badge/ntplib-0.4%2B-555555)](https://pypi.org/project/ntplib/)

Funcionamento das rotinas automáticas agendadas no servidor, da fila de jobs no banco e do envio de relatórios e alertas por e-mail e Telegram. As variáveis de horário e retenção estão em [`configuracao-e-limites.md`](configuracao-e-limites.md).

## Bibliotecas utilizadas

- `apscheduler`: agendador assíncrono (`AsyncIOScheduler`) com `CronTrigger` rodando no fuso definido em `TIMEZONE` (`America/Fortaleza` por padrão).
- `sqlalchemy` e `asyncpg`: persistência e consumo da tabela `background_jobs` usando `FOR UPDATE SKIP LOCKED`.
- `httpx`: envio assíncrono de mensagens e documentos para a API do Telegram (`sendMessage` e `sendDocument`) e busca de feriados nacionais na BrasilAPI.
- `smtplib` e `email` (biblioteca padrão): envio de e-mails SMTP TLS com anexos de log.
- `ntplib` e `tzlocal`: sincronização de horário em [`TrustedTimeService`](../app/shared/trusted_time_service.py), combinando o relógio do PostgreSQL com servidores NTP (`a.st1.ntp.br`, `b.st1.ntp.br` e `pool.ntp.org`).

## Subida do servidor e rotinas do APScheduler

No ciclo de inicialização da API ([`app/core/lifespan.py`](../app/core/lifespan.py)):

1. O serviço de horário (`trusted_time_service`) é iniciado.
2. Se `BACKGROUND_JOBS_ENABLED=true`, o worker da fila de banco (`job_queue.start_worker()`) começa a consumir os jobs pendentes em `background_jobs`.
3. O [`RoutineOrchestrator`](../app/features/system/routine_orchestrator.py) registra quatro rotinas no `AsyncIOScheduler` com `coalesce=True`, `max_instances=1` e `misfire_grace_time=3600`:

| Job | Horário | Função | O que faz |
| --- | --- | --- | --- |
| `daily_unclosed_records_check` | Todos os dias às `00:01` | `check_unclosed_records_job` | Procura jornadas do dia anterior que ficaram com batida ímpar (entrada sem saída), cria o ajuste pendente (`MISSING_EXIT`), recalcula o resumo do dia e salva o resultado em `routine_logs`. |
| `daily_reports_dispatch` | Todos os dias em `DAILY_REPORT_HOUR:00` (padrão `09:00`) | `send_daily_reports_job` | Monta o resumo operacional das últimas 24h, junta os logs do dia em um único anexo, envia por SMTP e Telegram e apaga registros de `routine_logs` mais antigos que `ROUTINE_LOG_RETENTION_DAYS`. |
| `hourly_database_backup` | Minuto `0` de cada hora entre `HOURLY_BACKUP_START_HOUR` e `HOURLY_BACKUP_END_HOUR` (padrão `06h-19h`) | `hourly_database_backup_job` | Gera o backup criptografado (`spe.zip.enc`) e envia o arquivo para o chat administrativo no Telegram. |
| `yearly_holidays_sync` | Dia `01/01` às `02:00` (e 10s após subir o servidor) | `sync_holidays_job` | Importa os feriados nacionais do ano atual pela BrasilAPI caso ainda não estejam cadastrados na tabela `holidays`. |

## Anexo único de logs diários

Quando há mais de um arquivo de log gerado no mesmo dia em `logs/`, [`notification_jobs.py`](../app/features/system/notification_jobs.py) e `_build_daily_log_attachment` em [`telegram_service.py`](../app/features/system/telegram_service.py) ordenam os arquivos da data, separam o conteúdo de cada um com o cabeçalho `===== <nome_do_arquivo> =====` e montam um único arquivo `spe_YYYY-MM-DD.log` para anexar no e-mail e no Telegram.

## Fila de jobs no banco (`background_jobs`)

Tarefas assíncronas criadas pelos controllers ou pelo agendador são salvas na tabela `background_jobs` via [`JobService`](../app/features/system/job_service.py) e executadas por [`job_queue.py`](../app/features/system/job_queue.py):

- Cada registro guarda `job_type`, `payload`, `status` (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`), `attempts`, `max_attempts`, `available_at`, `started_at`, `finished_at` e `last_error`.
- O worker busca os próximos jobs disponíveis com `SELECT ... FOR UPDATE SKIP LOCKED`, evitando que dois processos peguem o mesmo job.
- Se a execução falhar e ainda houver tentativas restantes (`attempts < max_attempts`), o job volta para `PENDING` com backoff em `available_at`; ao esgotar as tentativas, fica marcado como `FAILED`.
- O reprocessamento administrativo de apurações (`POST /api/v1/daily-summaries/admin/reprocess`) roda nessa mesma fila, processando os dias em lotes definidos por `REPROCESS_BATCH_SIZE` e respeitando os limites `REPROCESS_MAX_DAYS` e `REPROCESS_MAX_ITEMS`.

## Endpoints de controle e monitoramento

Os controllers em [`monitoring.py`](../app/features/system/monitoring.py) e [`system_router.py`](../app/features/system/system_router.py) expõem as rotas abaixo para mantenedores:

- `POST /api/v1/operations/jobs`: dispara manualmente `audit_open_records`, `send_daily_reports` ou `sync_holidays` e retorna `202 Accepted` com o ID do job criado.
- `GET /api/v1/operations`: retorna o status atual do banco, contadores da fila `background_jobs` e últimas rotinas executadas.
- `GET /api/v1/routine-logs/`: consulta os logs salvos em `routine_logs` filtrando por `routine_type`, `status`, `start_date` e `end_date`.
- `GET /api/v1/routine-logs/jobs/{job_id}`: mostra os detalhes e eventual erro de um job específico.
- `POST /api/v1/routine-logs/jobs/{job_id}/retry`: recoloca um job com falha para rodar novamente.
