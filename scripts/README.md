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

Confira no `.env` principalmente `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `SQLALCHEMY_DATABASE_URI` e a `SECRET_KEY` já usada pela API. Ela precisa ter pelo menos 32 bytes. Para restaurar um backup criptografado em outra máquina, copie a chave **original**; gerar uma chave nova não abre o arquivo. Numa instalação nova, preencha esse campo uma vez e guarde a chave fora do servidor. Nenhuma variável nova é necessária. Depois execute:

```bash
make setup && make db-init
```

Esse comando inicia o PostgreSQL e cria ou atualiza sua estrutura com o Alembic. Se o banco não iniciar, o Alembic não será executado. Depois, escolha abaixo somente a operação que deseja executar.

## Opção 1: restaurar um backup PostgreSQL recebido por e-mail

Salve o anexo com o nome `spe.zip.enc` dentro da pasta `scripts`:

```text
scripts/spe.zip.enc
```

Com a preparação inicial concluída, execute:

```bash
make restore
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

O comando gera `spe.zip.enc` com estrutura e dados de uma única fotografia do PostgreSQL. O arquivo é criptografado com a `SECRET_KEY` atual; os SQLs temporários são removidos ao final. Se `spe.zip.enc` já existir na raiz, o comando **não o sobrescreve**: guarde ou renomeie o arquivo anterior antes de gerar outro. Guarde a chave separadamente do backup e teste uma restauração periódica em um banco descartável.

Com `spe.zip.enc` na raiz ou em `scripts/`, teste sem alterar o banco principal:

```bash
make db-restore-test
```

O comando cria um banco temporário, aplica o Alembic e restaura os dados. Ao terminar, apaga somente esse banco temporário. O usuário PostgreSQL precisa de permissão para criar bancos.

## Encerrar o PostgreSQL

Quando terminar qualquer uma das operações:

```bash
make docker-down
```
