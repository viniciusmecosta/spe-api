# Banco de dados: uso, restauração e migração

## Antes de qualquer operação

Faça esta preparação antes de restaurar um backup, migrar um SQLite ou gerar um novo backup.

### 1. Abra o terminal na raiz do projeto

Todos os comandos deste documento devem ser executados na pasta que contém o `Makefile`.

### 2. Inicialize o ambiente

Tenha o Docker instalado. Se o arquivo `.env` ainda não existir, crie-o a partir do exemplo:

```bash
cp .env.example .env
```

Confira no `.env` principalmente `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` e `SQLALCHEMY_DATABASE_URI`. Depois execute:

```bash
make db-init
```

Esse comando inicia o PostgreSQL e cria ou atualiza sua estrutura com o Alembic. Se o banco não iniciar, o Alembic não será executado. Depois, escolha abaixo somente a operação que deseja executar.

## Opção 1: restaurar um backup PostgreSQL recebido por e-mail

Salve o anexo com o nome `spe.zip` dentro da pasta `scripts`:

```text
scripts/spe.zip
```

Com a preparação inicial concluída, execute:

```bash
make restore
```

O restore aceita `spe.zip` ou `spe_dump.sql` na raiz do projeto ou dentro de `scripts/`. Ele apaga os dados atuais do PostgreSQL, preserva a estrutura e o `alembic_version`, valida a revisão do backup e então insere os dados.

## Opção 2: migrar um banco SQLite para PostgreSQL

Coloque o banco SQLite com o nome `spe.db` na raiz do projeto:

```text
spe.db
```

Com a preparação inicial concluída, execute as três etapas:

```bash
make db-dump-sqlite && make db-apply-dump && make db-check
```

Elas convertem os dados do SQLite, limpam os dados atuais do PostgreSQL, importam o dump e comparam os dois bancos célula por célula.

Como atalho, o comando abaixo faz a preparação do PostgreSQL e todas essas etapas:

```bash
make db-migrate-all
```

O dump convertido é criado automaticamente em:

```text
scripts/data_inserts_postgresql.sql
```

## Opção 3: gerar um novo backup PostgreSQL

```bash
make dump
```

O comando gera `spe.zip` com a estrutura e os inserts do PostgreSQL, incluindo a revisão Alembic correta.

## Encerrar o PostgreSQL

Quando terminar qualquer uma das operações:

```bash
make docker-down
```
