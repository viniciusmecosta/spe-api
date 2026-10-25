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

Com a origem sem novas gravações e o PostgreSQL de destino novo, o comando aplica `001/002`, exporta e importa o SQLite,
aplica `003/004/005`, verifica a paridade e cria os resumos diários até a data atual. A revisão `003` remove os logins e
reenumera os IDs de auditoria intencionalmente; `004` preserva a precisão dos resumos e permite restaurar referências
entre batidas fora de ordem. A revisão `005` cria a fila durável de entregas e reprocessamentos. Os arquivos físicos
devem ser migrados manualmente. Inicie a API somente após o backfill e as verificações.

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

### Operação com NSSM e PostgreSQL nativo

Antes da atualização, interrompa novas gravações, preserve o banco de origem e copie o diretório completo de uploads.
Instale a mesma versão de Python usada nos testes (3.12 ou superior), sincronize as dependências e aplique
`alembic upgrade head` com a API parada. A revisão atual é `005`. Configure a conexão PostgreSQL na conta que executa o
NSSM, com acesso ao diretório de uploads e aos arquivos de log. O PostgreSQL deve iniciar antes da API.

Use `/api/v1/health` para verificar o processo e `/api/v1/ready` para verificar banco e revisão do schema. A área
Admin > Monitoramento consulta `/api/v1/operations`; esse endpoint e os detalhes das tarefas exigem mantenedor. A
configuração dos limites de pool e dos timeouts está no `.env.example`. Cada processo possui pools síncrono e assíncrono
próprios; dimensione o limite de conexões PostgreSQL considerando ambos.

A fila usa leases no PostgreSQL e guarda anexos em `UPLOAD_DIR/.delivery_queue`, fora da área pública. Preserve essa
pasta junto com os relatórios, anexos e firmwares ao migrar o serviço. As tarefas confirmadas não são reenviadas durante
a retomada normal. A reserva da tarefa é renovada enquanto o processamento está ativo. Os anexos de tarefas inteiramente confirmadas
são removidos; uma limpeza horária recupera sobras de interrupções sem remover arquivos de tarefas pendentes, parciais
ou incertas. Uma entrega interrompida após o envio pode ficar como incerta e exige conferência no destino. A ação
de nova tentativa no Admin retoma falhas confirmadas sem reenviar partes concluídas.

Ao restaurar um backup, pare a API ou configure `BACKGROUND_JOBS_ENABLED=false`. Confira as tarefas pendentes no
monitoramento antes de reativar o trabalhador, pois o backup representa o estado da fila no instante da captura. A
restauração e a troca do PostgreSQL precisam ser ensaiadas em um banco separado. Os testes locais não substituem a
validação de inicialização, permissões, parada e reinício do NSSM no Windows de produção.
