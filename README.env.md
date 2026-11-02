# Variáveis de ambiente

Copie [`.env.example`](.env.example) para `.env` e ajuste os valores. O arquivo de exemplo não contém credenciais de produção. Listas são escritas como JSON, por exemplo `["https://aplicativo.exemplo"]`. Valores em bytes usam unidades binárias.

## Aplicação e autenticação

| Variável | Finalidade |
| --- | --- |
| `PROJECT_NAME` | Nome exibido na documentação da API. |
| `APP_VERSION` | Versão informada pela API e pelo monitoramento. |
| `ENVIRONMENT` | Ambiente da aplicação: `PROD` ou `DEV`. |
| `TIMEZONE` | Fuso horário usado nos registros e rotinas. |
| `SECRET_KEY` | Chave de assinatura dos tokens e criptografia dos backups. |
| `ALGORITHM` | Algoritmo de assinatura JWT. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Validade do token de acesso, em minutos. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Validade absoluta da família de refresh tokens, de 1 a 365 dias. |
| `PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES` | Validade da sessão restrita à troca de senha, de 1 a 30 minutos. |
| `FIRST_SUPERUSER` | Nome de usuário do mantenedor inicial. |
| `FIRST_SUPERUSER_PASSWORD` | Senha do mantenedor inicial. |
| `BACKEND_CORS_ORIGINS` | Origens autorizadas pelo CORS. |
| `TRUSTED_PROXY_CIDRS` | Redes dos proxies autorizados a informar o IP de origem. |
| `RATE_LIMIT_ENABLED` | Habilita a limitação por origem; padrão `true`. Acesso direto por localhost é isento. |
| `RATE_LIMIT_REQUESTS_PER_SECOND` | Requisições permitidas por IP em um segundo; padrão `30`. |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Requisições gerais permitidas por IP em 60 segundos; padrão `600`. |
| `RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE` | Limite adicional compartilhado entre login, renovação e alteração de senha; padrão `60`. |

## PostgreSQL

| Variável | Finalidade |
| --- | --- |
| `SQLALCHEMY_DATABASE_URI` | URI de conexão PostgreSQL com driver `asyncpg`. |
| `POSTGRES_DB` | Nome do banco usado pelo Compose e pelas ferramentas PostgreSQL. |
| `POSTGRES_USER` | Usuário do PostgreSQL. |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL. |
| `POSTGRES_HOST` | Endereço do servidor PostgreSQL. |
| `POSTGRES_PORT` | Porta do PostgreSQL. |
| `DB_POOL_SIZE` | Conexões mantidas em cada pool. |
| `DB_MAX_OVERFLOW` | Conexões adicionais permitidas por pool. |
| `DB_POOL_TIMEOUT_SECONDS` | Tempo máximo para obter conexão do pool. |
| `DB_CONNECT_TIMEOUT_SECONDS` | Tempo máximo para abrir uma conexão. |
| `DB_STATEMENT_TIMEOUT_MS` | Tempo máximo de uma consulta, em milissegundos. |
| `DB_LOCK_TIMEOUT_MS` | Tempo máximo de espera por bloqueio, em milissegundos. |
| `DB_IDLE_TRANSACTION_TIMEOUT_MS` | Tempo máximo de uma transação ociosa, em milissegundos. |

## Arquivos e uploads

| Variável | Finalidade |
| --- | --- |
| `UPLOAD_DIR` | Diretório dos arquivos enviados e gerados. |
| `UPLOAD_REQUEST_MAX_BYTES` | Limite total do corpo de uma requisição. |
| `UPLOAD_LOGO_MAX_BYTES` | Limite de arquivo para logo. |
| `UPLOAD_ATTACHMENT_MAX_BYTES` | Limite de arquivo para anexo de ajuste. |
| `UPLOAD_FIRMWARE_MAX_BYTES` | Limite de arquivo para firmware. |
| `UPLOAD_LEGACY_REPORT_MAX_BYTES` | Limite de arquivo para relatório legado de folha. |
| `UPLOAD_LOGO_MAX_DIMENSION` | Maior dimensão permitida do logo, em pixels. |
| `UPLOAD_LOGO_MAX_PIXELS` | Quantidade máxima de pixels do logo. |

## Notificações e tarefas

| Variável | Finalidade |
| --- | --- |
| `SMTP_HOST` | Servidor SMTP para mensagens e backups. |
| `SMTP_PORT` | Porta do servidor SMTP. |
| `SMTP_USER` | Usuário SMTP. |
| `SMTP_PASSWORD` | Senha ou credencial SMTP. |
| `EMAIL_FROM` | Endereço remetente das mensagens. |
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram. |
| `TELEGRAM_CHAT_ID` | Identificador do destino no Telegram. |
| `TELEGRAM_MAX_MESSAGE_LENGTH` | Limite de caracteres por mensagem Telegram. |
| `ROUTINE_LOG_RETENTION_DAYS` | Retenção dos registros de rotina, em dias. |
| `DAILY_REPORT_HOUR` | Hora local de envio do relatório diário. |
| `HOURLY_BACKUP_START_HOUR` | Primeira hora local da janela de backups horários. |
| `HOURLY_BACKUP_END_HOUR` | Última hora local da janela de backups horários. |
| `BACKGROUND_JOBS_ENABLED` | Habilita o processamento das tarefas em segundo plano. |
| `REPROCESS_MAX_DAYS` | Limite de dias em uma solicitação de reprocessamento. |
| `REPROCESS_MAX_ITEMS` | Limite de itens em uma solicitação de reprocessamento. |
| `REPROCESS_BATCH_SIZE` | Quantidade de itens por lote de reprocessamento. |

Em `DEV`, a autenticação de funcionários admite o acesso sem conferir a senha, exceto quando há redefinição obrigatória. Use `PROD` no ambiente real.

Mantenha segredos fora do controle de versão. Para caracteres reservados na senha da URI, use codificação percentual. O processamento de tarefas pode ser pausado com `BACKGROUND_JOBS_ENABLED=false` durante verificações de recuperação.
