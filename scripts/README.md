# Banco de dados: uso, restauração e migração

## Antes de qualquer operação

Faça esta preparação antes de restaurar um backup, migrar um SQLite ou gerar um novo backup.

### 1. Abra o terminal na raiz do projeto

Todos os comandos deste documento devem ser executados na pasta que contém o `Makefile`.

### 2. Inicialize o ambiente

Em produção, use o PostgreSQL externo já provisionado e o cliente nativo `pg_dump` instalado na máquina/container da API (versão compatível com o servidor). O Compose é apenas uma opção local de desenvolvimento. Se o arquivo `.env` ainda não existir, crie-o a partir do exemplo:

```bash
cp .env.example .env
```

Configure `SQLALCHEMY_DATABASE_URI` para o PostgreSQL correto; a API, o backup e os scripts usam esse URI como fonte de verdade. Codifique os caracteres reservados da senha no URI. Use `TIMEZONE=America/Fortaleza`. Confira também a `SECRET_KEY` já usada pela API: ela precisa ter pelo menos 32 bytes. Para restaurar um backup criptografado em outra máquina, use a chave **original**. Depois execute:

```bash
make setup
```

Esse comando instala as dependências travadas. Os comandos de banco não iniciam o Docker nem provisionam o PostgreSQL. A estrutura é criada na etapa específica de cada operação. Para desenvolvimento local com Compose, inicie o serviço explicitamente com `make db-pg-up`.

## Opção 1: restaurar um backup PostgreSQL recebido por e-mail

Salve o anexo com o nome `spe.zip.enc` dentro da pasta `scripts`:

```text
scripts/spe.zip.enc
```

Com a preparação inicial concluída, crie a estrutura e restaure:

```bash
make db-init && make restore
```

O restore também aceita `spe.zip` ou `spe_dump.sql` antigos, mas exige confirmação especial por não terem manifesto. Para `spe.zip.enc`, ele autentica e descriptografa o pacote com a `SECRET_KEY`, valida o manifesto, preserva a estrutura e o `alembic_version`, insere os dados em transação e compara a quantidade de linhas de cada tabela. Se alguma validação falhar, desfaz a transação.

Para um backup antigo, somente depois de confirmar que o arquivo é confiável e completo, use:

```bash
.venv/bin/python scripts/apply_sql_to_postgresql.py --file scripts/spe.zip --yes --allow-unverified-dump
```

Esse modo antigo não consegue comprovar que todas as tabelas estavam presentes. Não o use com arquivos parciais.

## Opção 2: migrar um banco SQLite para PostgreSQL

Coloque o banco SQLite com o nome `spe.db` na raiz do projeto:

```text
spe.db
```

Com a preparação inicial concluída, execute:

```bash
make db-migrate-all
```

Com a origem sem novas gravações e o PostgreSQL de destino novo, o comando aplica `001/002`, exporta e importa o SQLite, aplica `003/004`, verifica a paridade e cria os resumos diários até a data atual. A revisão `003` remove os logins e reenumera os IDs de auditoria intencionalmente; `004` preserva a precisão dos resumos e permite restaurar referências entre batidas fora de ordem. Os arquivos físicos devem ser migrados manualmente. Inicie a API somente após o backfill e as verificações.

Para um PostgreSQL que já esteja na revisão `003`, aplique `make upgrade` e execute `.venv/bin/python -m scripts.backfill_daily_summaries --execute` antes de liberar a API. O backfill reconstrói os resumos com a precisão nova, inclusive os períodos fechados, sem alterar as batidas e os ajustes da origem. As revisões `001` e `003` continuam sem downgrade automático.

O dump convertido é criado automaticamente em:

```text
scripts/data_inserts_postgresql.sql
```

## Opção 3: gerar um novo backup PostgreSQL

```bash
make dump
```

O comando gera `spe.zip.enc` com estrutura e dados de uma única fotografia do PostgreSQL. O arquivo é criptografado com a `SECRET_KEY` atual; os SQLs temporários são removidos ao final. Se `spe.zip.enc` já existir na raiz, o comando **não o sobrescreve**: guarde ou renomeie o arquivo anterior antes de gerar outro. Guarde a chave separadamente do backup e teste uma restauração periódica em um banco descartável.

Com `spe.zip.enc` na raiz ou em `scripts/`, teste sem alterar o banco principal:

```bash
make db-restore-test
```

O comando cria um banco temporário, aplica o Alembic e restaura os dados. Ao terminar, apaga somente esse banco temporário. O usuário PostgreSQL precisa de permissão para criar bancos.

## Encerrar o PostgreSQL

Somente se o PostgreSQL local tiver sido iniciado pelo Compose:

```bash
make docker-down
```
