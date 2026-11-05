# Backup criptografado e restore do PostgreSQL

[![Cryptography](https://img.shields.io/badge/Cryptography-45.0%2B-3776AB)](https://cryptography.io/) [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/) [![psycopg2](https://img.shields.io/badge/psycopg2-2.9%2B-336791)](https://www.psycopg.org/) [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)](https://www.sqlalchemy.org/) [![GNU Make](https://img.shields.io/badge/Make-automação-A42E2B)](https://www.gnu.org/software/make/)

Funcionamento da geração de dump, compactação, criptografia, validação de manifesto e restore do PostgreSQL no SPE. Sobre o agendamento do backup de hora em hora, veja [`rotinas-e-cron.md`](rotinas-e-cron.md).

## Bibliotecas utilizadas

- `cryptography` (`Fernet`): criptografia simétrica autenticada (`AES-128-CBC` + `HMAC-SHA256`) do pacote `.zip` gerado no dump.
- `hashlib` e `base64` (biblioteca padrão): derivação da chave Fernet a partir de `SECRET_KEY` (`SHA-256` em Base64 URL-safe) e cálculo dos hashes `SHA-256` salvos no manifesto.
- `zipfile` (biblioteca padrão): compactação do dump SQL, do manifesto e da pasta `uploads/` antes de criptografar.
- `psycopg2-binary` e `sqlalchemy`: leitura das tabelas, contagem de registros e execução dos scripts SQL durante o restore e o teste em banco temporário.

## Como o arquivo `spe.zip.enc` é gerado

O script [`scripts/db_manager.py`](../scripts/db_manager.py) e o [`BackupService`](../app/features/system/backup_service.py) montam o arquivo `spe.zip.enc` em quatro passos:

1. Dump SQL: exporta o schema (DDL), os dados das tabelas respeitando a ordem das chaves estrangeiras e o ajuste das sequences (`setval`) do banco PostgreSQL configurado no `.env`.
2. Arquivos de upload: inclui os arquivos da pasta `UPLOAD_DIR` (comprovantes, atestados, logo da empresa e firmwares OTA).
3. Manifesto de integridade: gera um JSON com o hash `SHA-256` do SQL, os hashes dos arquivos incluídos e a quantidade de linhas de cada tabela no momento do dump.
4. Compactação e criptografia: junta tudo em um `.zip` temporário, criptografa com `Fernet` usando a chave derivada da `SECRET_KEY`, salva como `spe.zip.enc` (com permissão `0600`) e apaga os arquivos temporários.

## Comandos do `Makefile`

Os atalhos do [`Makefile`](../Makefile) rodam os scripts direto no `.venv`:

```bash
# Gera o backup completo criptografado (spe.zip.enc)
make dump

# Exporta só a estrutura (DDL) do PostgreSQL
make db-dump-ddl

# Exporta só os INSERTs com os dados atuais
make db-dump-data

# Testa o backup restaurando em um banco temporário sem mexer no banco principal
make db-restore-test

# Restaura o spe.zip.enc no banco configurado no .env
make restore
```

## Validação e restore (`apply_sql_to_postgresql.py` e `verify_backup_restore.py`)

Ao rodar `make restore`, o script [`scripts/apply_sql_to_postgresql.py`](../scripts/apply_sql_to_postgresql.py) valida o pacote antes de escrever no banco:

1. Procura o `spe.zip.enc` na raiz do projeto ou em `scripts/spe.zip.enc`.
2. Descriptografa o pacote com a `SECRET_KEY` do `.env`. Se a chave estiver errada ou o arquivo tiver sido corrompido, a assinatura HMAC do Fernet aborta a execução na hora.
3. Compara o `SHA-256` do SQL extraído com o valor salvo no manifesto do pacote.
4. Aplica a estrutura e os dados no PostgreSQL e restaura o conteúdo da pasta `uploads/`.

Para testar se um backup está íntegro sem alterar o banco em uso, `make db-restore-test` ([`scripts/verify_backup_restore.py`](../scripts/verify_backup_restore.py)) sobe um banco temporário no PostgreSQL, restaura o `spe.zip.enc` nele, confere se a contagem de registros de todas as tabelas bate com o manifesto e apaga o banco temporário no final.

## Backup automático de hora em hora

Com a API rodando, o job `hourly_database_backup` do `APScheduler` gera um novo `spe.zip.enc` no minuto `0` de cada hora entre `HOURLY_BACKUP_START_HOUR` e `HOURLY_BACKUP_END_HOUR` (padrão das 06h às 19h) e envia o arquivo para o grupo configurado no Telegram (`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`).
