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

Os comandos abaixo destinam-se a um backup da revisão atual `008` e a um PostgreSQL de recuperação separado. Pare a API ou mantenha `BACKGROUND_JOBS_ENABLED=false`, confira o destino e preserve os dados existentes antes de restaurar: a operação substitui os dados do banco configurado. O backup não inclui os arquivos físicos de `UPLOAD_DIR`, que devem ser recuperados separadamente, inclusive `.delivery_queue`.

Com a preparação inicial concluída, crie a estrutura compatível e restaure:

```bash
make db-init && make restore
```

Se o backup foi produzido em uma revisão antiga, crie primeiro o schema da revisão correspondente usando o código compatível com aquele backup; restaure antes de aplicar as migrações posteriores. Não aplique `head` indiscriminadamente a esse destino: o importador valida tabelas e revisão e pode rejeitar a combinação. Não use `alembic stamp` para esconder uma incompatibilidade. Depois da restauração e da atualização para `008`, execute o backfill quando necessário e confira a fila antes de liberar as rotinas.

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
aplica `003/004/005/006/007/008`, verifica a paridade e cria os resumos diários até a data atual. O exportador já remove os logins e reenumera os IDs de auditoria intencionalmente; `003` assegura essa limpeza e cria os resumos; `004` preserva a precisão dos resumos e permite restaurar referências
entre batidas fora de ordem. A revisão `005` cria a fila durável de entregas e reprocessamentos; `006` adiciona a versão de autenticação, `007` vincula ajustes às batidas aplicadas e `008` remove `platform`/`is_verified` das batidas. O resultado deve ser `008 (head)`, sem diferenças em `alembic check`. Os arquivos físicos
devem ser migrados manualmente. Inicie a API somente após o backfill e as verificações.

Na produção com NSSM, siga os comandos do [guia Windows](../docs/implantacao_postgresql_windows10.md), com paridade em `002` e `005` antes de aplicar separadamente `006`, `007` e `008`. Depois execute o backfill e repita a paridade. O código atual exige as colunas de `006/007` para o backfill. O exportador mantém as duas colunas legadas no SQL inicial; a revisão `008` efetua sua remoção. O verificador aceita essas diferenças previstas, mas rejeita demais divergências. O downgrade de `008` não restaura os valores originais dessas colunas.

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

Para um backup compatível com o `head` do código em uso, o comando cria um banco temporário, aplica o Alembic e restaura os dados. Backups de revisões antigas exigem o ensaio com o schema correspondente descrito acima. Ao terminar, apaga somente esse banco temporário. O usuário PostgreSQL precisa de permissão para criar bancos.

## Encerrar o PostgreSQL

Somente se o PostgreSQL local tiver sido iniciado pelo Compose:

```bash
make docker-down
```

### Operação com NSSM e PostgreSQL nativo

Antes da atualização, interrompa novas gravações, preserve o banco de origem e copie o diretório completo de uploads.
Instale a mesma versão de Python usada nos testes (3.12 ou superior), sincronize as dependências e aplique
`alembic upgrade head` com a API parada. A revisão atual é `008`. Para uma migração SQLite, importe os dados em `002` antes de avançar para `head`; os comandos desta seção de atualização não substituem essa sequência. Configure a conexão PostgreSQL na conta que executa o
NSSM, com acesso ao diretório de uploads e aos arquivos de log. O PostgreSQL deve iniciar antes da API.

Use `/api/v1/health` para verificar o processo e `/api/v1/ready` para verificar banco e revisão do schema. A área
Admin > Monitoramento consulta `/api/v1/operations`; esse endpoint e os detalhes das tarefas exigem mantenedor. A
configuração dos limites de pool e dos timeouts está no `.env.example`. Cada processo possui pools síncrono e assíncrono
próprios; dimensione o limite de conexões PostgreSQL considerando ambos.

A fila usa leases no PostgreSQL e guarda anexos em `UPLOAD_DIR/.delivery_queue`, fora da área pública. Preserve essa
pasta junto com os relatórios, anexos e firmwares ao migrar o serviço. As tarefas confirmadas não são reenviadas durante
a retomada normal. A cron também respeita os sucessos já importados em `routine_logs`, evitando repetir a entrega
diária ou horária na transição da versão antiga. Esse histórico continua indicando o último período entregue e
alimenta o acompanhamento administrativo; as pendências e as tentativas ficam na fila durável. A reserva da tarefa é
renovada enquanto o processamento está ativo. Os anexos de tarefas inteiramente confirmadas
são removidos; uma limpeza horária recupera sobras de interrupções sem remover arquivos de tarefas pendentes, parciais
ou incertas. Uma entrega interrompida após o envio pode ficar como incerta e exige conferência no destino. A ação
de nova tentativa no Admin retoma falhas confirmadas sem reenviar partes concluídas. Esta versão não possui ação
administrativa de confirmar recebimento ou autorizar reenvio de partes `UNCERTAIN`; confira o destino, sem alterar
manualmente a fila.

Ao restaurar um backup, pare a API ou configure `BACKGROUND_JOBS_ENABLED=false`. Confira as tarefas pendentes no
monitoramento antes de reativar o trabalhador, pois o backup representa o estado da fila no instante da captura. A
restauração e a troca do PostgreSQL precisam ser ensaiadas em um banco separado. Os testes locais não substituem a
validação de inicialização, permissões, parada e reinício do NSSM no Windows de produção.

### Integridade de ajustes e sessões

A revisão 006 adiciona a versão de autenticação do usuário. Tokens existentes continuam válidos enquanto a
senha não mudar; alterações ou resets de senha encerram as sessões anteriores. O Flutter renova a sessão do
próprio usuário com a senha recém-definida, respeitando a preferência de lembrar acesso. Não há limitador de
frequência no login.

A revisão 007 vincula ajustes às batidas aplicadas. Aprovação, reversão, apuração e auditoria compartilham uma
transação. Aprovações concorrentes de uma solicitação não criam batidas duplicadas. O limite já existente de
10 horas de abono por dia é validado também sob concorrência. Valores negativos, não finitos e períodos
invertidos são rejeitados antes da gravação. Os relatórios distinguem horas brutas, que incluem abonos
aprovados, das horas contabilizadas após as regras. Na comparação com a API antiga, alguns campos de horas
trabalhadas diferiram porque antes exibiam o valor contabilizado; confira os dois totais na homologação antes
de liberar a migração. Os Excel antigos arquivados são preservados, e os novos são ordenados alfabeticamente.
A renderização Excel é executada fora do event loop.

No resumo de horas da equipe, `team_total_hours` representa o total contabilizado em horas decimais e
`team_formatted_time` inclui os minutos quando necessário. Por exemplo, 50 minutos são retornados como
`0.8333333333333334` e `0h 50min`. As barras individuais continuam exibindo horas inteiras.

### Uploads, proxy e exportações

Configure `UPLOAD_REQUEST_MAX_BYTES` para o total da requisição e os limites por categoria no `.env.example`.
Os padrões são 32 MiB por requisição, 5 MiB para logo, 10 MiB para anexo, 16 MiB para firmware e 25 MiB para
folha legada. Imagens têm limite de 4.096 pixels por dimensão e 16 milhões de pixels. A validação confere o
conteúdo; arquivos rejeitados ou transações desfeitas não deixam a referência nova registrada.

`TRUSTED_PROXY_CIDRS` deve conter somente as redes dos proxies que realmente encaminham conexões para a API.
Sem essa configuração, o IP utilizado é o remetente da conexão. Isso impede que um cliente escolha o IP
registrado enviando diretamente `X-Forwarded-For`.

A exportação ZIP mantém HTTP 200 para sucesso completo ou parcial. Os cabeçalhos `X-Export-Status`,
`X-Export-Generated-Count` e `X-Export-Failed-Count` informam o resultado; falhas parciais incluem
`manifesto_exportacao.json`. Se nenhum PDF puder ser gerado, a API retorna 503. O Flutter informa os casos
parciais. Os arquivos Excel históricos permanecem preservados.

O cabeçalho `X-Request-ID` identifica requisições e pode acompanhar tarefas admitidas pela fila. O log comum não exibe esse identificador; seus horários usam `TIMEZONE=America/Fortaleza`, sem depender do fuso do sistema ou container. O identificador
não contém credenciais e não substitui o identificador persistente do job.

### Sequência no Windows para PostgreSQL já implantado

Use Git Bash na raiz da instalação, com o serviço NSSM parado e o banco preservado. Confira o diretório de trabalho,
a conta do serviço, um único worker sem `--reload` e a inicialização do PostgreSQL antes da API. `pg_dump.exe`
deve estar acessível no ambiente da conta do NSSM, não apenas no terminal do administrador.

```bash
uv.exe sync --locked --no-dev --no-build --no-python-downloads --python .venv/Scripts/python.exe
.venv/Scripts/alembic.exe current
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe current
.venv/Scripts/alembic.exe check
```

Se o banco estava antes de `004`, reconstrua os resumos antes de iniciar a API:

```bash
.venv/Scripts/python.exe -m scripts.backfill_daily_summaries
.venv/Scripts/python.exe -m scripts.backfill_daily_summaries --execute
```

Inicie o serviço com `BACKGROUND_JOBS_ENABLED=false`, confira `/api/v1/health`, `/api/v1/ready` e os fluxos autenticados
pelo IP real da rede local. Preserve `BACKEND_CORS_ORIGINS` usado pelos clientes e implante o Flutter compatível com a
renovação de sessão e os resultados parciais das exportações. Mantenha os Excel arquivados sem alteração.

No Admin > Monitoramento, confira histórico e pendências antes de definir `BACKGROUND_JOBS_ENABLED=true` e reiniciar
para carregar a configuração. A opção pausa somente o consumidor; o agendador ainda pode admitir tarefas. A cron
verifica rotinas a cada dez minutos e o consumidor consulta a fila a cada cinco segundos. O retorno de `job_id`
confirma admissão, não entrega concluída. Os detalhes ficam em `GET /api/v1/routine-logs/jobs/{job_id}`; a nova tentativa
para falhas confirmadas usa `POST /api/v1/routine-logs/jobs/{job_id}/retry`, com permissão de mantenedor.

Confira os destinatários nos mantenedores ativos com e-mail cadastrado, a configuração SMTP/Telegram, empresa/logo e
`APP_VERSION` da versão implantada. `EMAIL_TO` não existe na configuração atual. Ensaie a próxima entrega autorizada e
a retomada após reinício; uma reserva interrompida pode levar até cinco minutos para expirar. O teste no Windows de
produção continua necessário mesmo com testes automatizados aprovados. Após novas gravações no PostgreSQL, qualquer
retorno ao SQLite exige reconciliar os dados novos.
