**Auditoria da migração PostgreSQL e da apuração — 16/10/2026**

**Atualização após as correções:** este documento preserva os achados do commit original. As correções aplicadas, as decisões confirmadas pelo responsável e os novos resultados estão em [correcoes.md](correcoes.md). O parecer abaixo é histórico e não descreve o estado final corrigido.

**Parecer: não liberar esta versão para produção antes de corrigir os quatro achados P1.** A transferência dos dados disponíveis passou, mas foram reproduzidas falhas de integridade da folha e de restauração. Os demais achados precisam entrar na correção e na validação da entrega.

Auditado: `feature/apuracao`, commit `8a3b172bba8c33345cc3cc7dc1a67e4ff058e347`, comparado à `main` local `ba2bcb9bebb7801d470ce46cdd2eb1d34ab3e2a7`. São 180 arquivos alterados, incluindo migração, apuração, relatórios, backups, infraestrutura e testes. O checkout estava limpo e sete commits à frente da referência local de `origin/feature/apuracao`. Este parecer se refere ao commit local completo; a atualização das referências remotas não foi confirmada nesta auditoria.

Foram aplicadas as skills solicitadas: `fastapi-pro`, `python-fastapi-development`, `python-pro`, `database-admin`, `postgresql` e `postgresql-optimization`. A aplicação não foi corrigida ou implantada. Os arquivos adicionados são o relatório e suas evidências sanitizadas.

**O que foi executado e passou**

| Verificação | Resultado e alcance |
| --- | --- |
| PostgreSQL real | PostgreSQL 17.11, em container exclusivo da auditoria, acessível somente em `127.0.0.1:55439`. |
| Runtime de produção | Dependências instaladas com `uv sync --python 3.12 --locked --no-build` em ambiente separado; Python 3.12.13. |
| Migrações novas | `001 → 002 → 003` aplicadas em banco vazio. |
| SQLite disponível | `spe.db`, revisão `045`, acessado para leitura; zero violações em `PRAGMA foreign_key_check`. |
| Migração dos dados disponíveis | Exportação, importação na revisão `002`, upgrade para `003` e comparação célula a célula: **5.550 linhas, zero divergências**, considerando a exclusão de logins prevista pelo código. |
| Backfill | 4.046 resumos, de janeiro a 16/10/2026, para os 14 usuários da cópia. |
| Comparação histórica | `compare_history_summaries`: **280 comparações de histórico/relatório avançado, zero diferenças** na cópia disponível. Compara o cálculo legado com a leitura materializada na branch. Não é uma comparação visual de todos os PDFs e Excels da `main`. |
| Backup completo da cópia | Snapshot consistente, schema + dados, criptografia, descriptografia e restore em outro banco: **15 tabelas e 9.596 linhas** com contagens e checksums do conteúdo iguais. |
| Sequências após restore | As 15 sequências verificadas produziram próximo ID maior que o máximo existente. |
| Índices de FKs | Nenhuma FK sem índice com prefixo compatível no schema criado. |
| Planos de consultas | Consultas por usuário/período usaram `uq_daily_summaries_user_date` e `idx_tr_active_period`. Aproximadamente 0,14 ms e 0,13 ms na pequena cópia local; não constituem benchmark de produção. |
| Tipagem | Mypy passou em 144 arquivos, com as supressões já configuradas no projeto. |
| Imagem | `docker build` passou. A imagem executou Alembic, seed e servidor em ambiente isolado; health, login e consulta autenticada de usuários retornaram HTTP 200. |

O transporte do `pg_dump` no ensaio de backup foi direcionado explicitamente ao container de auditoria. Não foi usado o fallback com nome fixo `spe_postgres`, que pertence ao ambiente existente. Não houve envio de e-mails ou mensagens.

**Achados confirmados e correções necessárias**

**A01 — P1: backup válido pode não restaurar batidas editadas.**

Referências: [FK da batida original](/home/vini/dev/MH7/SPE/alembic/versions/001_db_base.py:84), [restore](/home/vini/dev/MH7/SPE/scripts/apply_sql_to_postgresql.py:547).

Reprodução: foram criadas uma batida original `100`, uma edição `101` apontando para `100`, e uma atualização posterior na original. A leitura física retornou a edição antes da original. O `pg_dump --data-only --inserts --column-inserts` terminou com sucesso, mas o restore falhou com `ForeignKeyViolation`, constraint `fk_time_records_original_record_id`. O PostgreSQL também emitiu o aviso de referência circular.

Causa: a FK é imediata, sem `DEFERRABLE`. O comando `SET CONSTRAINTS ALL DEFERRED` do restore não adia constraints que não foram definidas como adiáveis. A ordem física das linhas não é uma garantia de ordem de dependência.

Correção: adicionar uma nova migração tornando essa FK adiável, e mantê-la adiada durante o restore, ou implementar uma importação que resolva as referências em duas etapas. Só ordenar por ID não cobre referências arbitrárias válidas. Validar restore após atualizações, com filho antes do pai e dependências atravessando lotes. [Comportamento oficial de SET CONSTRAINTS](https://www.postgresql.org/docs/17/sql-set-constraints.html), [limitações do dump somente de dados](https://www.postgresql.org/docs/17/app-pgdump.html).

**A02 — P1: datetime em UTC permite inserir batida em mês fechado.**

Referências: [validação na criação administrativa](/home/vini/dev/MH7/SPE/app/features/time_records/time_record_admin_service.py:196), [edição](/home/vini/dev/MH7/SPE/app/features/time_records/time_record_admin_service.py:234), [schemas de entrada](/home/vini/dev/MH7/SPE/app/features/time_records/time_record_schemas.py:28).

Reprodução: janeiro fechado, fevereiro aberto, entrada administrativa com `2026-02-01T00:30:00Z`. A validação consultou fevereiro, mas o instante persistido, no fuso da aplicação, foi **31/01/2026 às 21:30**. A operação passou. O recálculo então ignorou janeiro porque estava fechado.

Correção: normalizar datetimes para `settings.TIMEZONE` antes de qualquer `.date()`, comparação, invalidação ou gravação. Aplicar isso a `TimeRecordCreateAdmin` e `TimeRecordUpdate`, além dos demais pontos de entrada; a normalização existente em `TimeRecordSimple` não protege essas entradas. Testar virada de dia, mês e ano em UTC e em outros offsets, tanto na criação quanto na edição.

**A03 — P1: falha ou interrupção do recálculo pode deixar resumo antigo sendo usado como válido.**

Referências: [commit da sessão](/home/vini/dev/MH7/SPE/app/database/session.py:42), [despacho após commit](/home/vini/dev/MH7/SPE/app/features/daily_summaries/daily_summary_events.py:103), [retentativas](/home/vini/dev/MH7/SPE/app/features/daily_summaries/daily_summary_events.py:63), [leitura do resumo](/home/vini/dev/MH7/SPE/app/features/daily_summaries/daily_summary_service.py:108).

Reprodução: resumo inicial de zero; duas batidas representando oito horas; falha controlada nas três tentativas de recálculo. O commit lançou `DailySummaryRecalculationError`, mas as duas batidas ficaram gravadas. O resumo continuou em zero, sem tarefa pendente. Um novo commit não tentou novamente. Uma nova leitura retornou zero horas, mesmo recebendo as duas batidas.

Causa: a alteração é confirmada antes do recálculo; os dias pendentes ficam só em memória e são removidos da sessão. A leitura detecta ausência de resumo, mas não detecta resumo desatualizado. A mensagem HTTP 503 informa a gravação parcial, porém não recupera a consistência nem garante a auditoria executada depois desse commit.

Correção: tornar a atualização consistente na própria transação ou registrar invalidação/outbox durável junto da alteração original. Na alternativa assíncrona, persistir versão/estado pendente, retomar trabalhos após reinício e impedir que relatórios e fechamento consumam resumos pendentes como válidos. Garantir idempotência de retentativas e auditoria da gravação original. Validar falha, cancelamento e reinício entre commit e processamento.

**A04 — P1: fechamento concorrente com gravação pode congelar apuração incompleta.**

Referências: [verificação de folha fechada no recálculo](/home/vini/dev/MH7/SPE/app/features/daily_summaries/daily_summary_service.py:401), [geração e gravação do fechamento](/home/vini/dev/MH7/SPE/app/features/payroll/payroll_service.py:193).

Reprodução com duas sessões reais: a primeira validou março como aberto; a segunda fechou março; a primeira gravou duas batidas totalizando oito horas e concluiu o commit **sem erro**. O recálculo encontrou o fechamento e retornou sem atualizar o resumo, que permaneceu em zero.

A janela entre validar e gravar já existia nos serviços; a materialização passa a congelar também um resumo incompatível com as batidas. O índice único de fechamento impede dois fechamentos ativos, mas não serializa fechamento e alterações de ponto.

Correção: usar coordenação transacional por competência em todos os escritores e no fechamento, repetir a validação dentro dessa proteção e garantir que o Excel oficial seja gerado com os mesmos dados consolidados que estão sendo fechados. Se houver processamento assíncrono, o fechamento precisa verificar e aguardar a resolução das pendências. Testar as duas ordens concorrentes, incluindo ajustes e mudanças de expediente.

**A05 — P2: arredondamento diário altera totais de expedientes fracionários.**

Referências: [conversão para minutos](/home/vini/dev/MH7/SPE/app/features/daily_summaries/daily_summary_service.py:39), [origem das horas decimais do expediente](/home/vini/dev/MH7/SPE/app/features/users/user_work_schedule_service.py:75).

Reprodução: dez dias com `daily_hours=8.08`, valor possível após arredondar um expediente de 8h05. O legado totalizou **4.848 minutos esperados**; os resumos arredondados por dia totalizaram **4.850**. As horas faltantes passaram de `80.80` para `80.83`. A base disponível não apresentou essa divergência nas 280 comparações, mas o caso sintético a reproduziu.

Correção: definir uma única regra de precisão e agregação. Preferir duração exata em minutos/segundos na origem do expediente e evitar arredondamentos intermediários incompatíveis. Para o histórico existente, comparar totais por período e tratar explicitamente qualquer mudança de regra; não reescrever silenciosamente valores oficiais fechados. Adicionar casos de expedientes com minutos não inteiros quando expressos em horas decimais.

**A06 — P2: porta externa do PostgreSQL pode quebrar backups dentro do container.**

Referências: [resolução de credenciais](/home/vini/dev/MH7/SPE/app/features/system/backup_service.py:155), [ambiente da API no Compose](/home/vini/dev/MH7/SPE/docker-compose.yml:36).

O Compose aponta o URI da API para `db:5432`, mas o helper de backup prioriza `POSTGRES_PORT` do `.env`, usado também como porta publicada no host. Com uma publicação em `55439`, a API usa `5432` e o backup tenta `55439` dentro da rede Docker. Essa divergência foi reproduzida na resolução dos parâmetros. A configuração padrão em `5432` não apresenta o problema.

Correção: separar porta interna de porta publicada e definir uma única fonte de verdade para a conexão de cada processo. No mínimo, sobrescrever `POSTGRES_PORT=5432` no serviço API; preferencialmente, derivar as credenciais do mesmo URI utilizado pela aplicação. Aplicar a regra aos helpers duplicados dos scripts e validar banco/host de destino. Testar uma porta publicada diferente de `5432`.

**A07 — P2: tratamento do conflito de fechamento usa atributos do driver errado.**

Referência: [tratamento de IntegrityError](/home/vini/dev/MH7/SPE/app/features/payroll/payroll_service.py:221).

O código procura `exc.orig.diag.constraint_name`, padrão do psycopg2. A API usa asyncpg pelo adaptador do SQLAlchemy. No conflito real reproduzido, esse atributo foi `None`; `sqlstate` era `23505` e a constraint estava em `exc.orig.__cause__.constraint_name`. Assim, o conflito do índice `uq_payroll_closures_active_period` é relançado como erro interno, em vez do `PayrollAlreadyClosedError` previsto, HTTP 400.

Correção: extrair SQLSTATE e constraint respeitando o adaptador asyncpg e sua cadeia de causas, sem converter qualquer violação de unicidade em “folha já fechada”. Testar duas chamadas concorrentes do serviço completo, a resposta de domínio e a remoção apenas do arquivo perdedor.

**A08 — P2: tratamento de diretivas psql confunde texto do usuário com comandos.**

Referências: [parser do restore](/home/vini/dev/MH7/SPE/scripts/apply_sql_to_postgresql.py:396), [limpeza do backup](/home/vini/dev/MH7/SPE/app/features/system/backup_service.py:143).

Um literal SQL válido com quebra de linha e uma linha começando com `\network-path` foi rejeitado como comando psql. Uma linha começando com `\restrict` dentro de um literal foi removida pelo limpador do backup, alterando seu conteúdo. Como o manifesto é calculado depois dessa limpeza, ele pode autenticar o conteúdo já alterado. Justificativas e observações podem conter texto multilinha.

Correção: reconhecer diretivas somente fora de strings, identificadores, comentários e dollar quotes, usando o estado léxico do parser. Revisar também `_iter_sql_file_statements` e os limpadores de `db_manager.py`. Validar roundtrip com quebras de linha, barras invertidas, aspas, ponto e vírgula e textos iniciados por `\restrict`/`\unrestrict` dentro dos valores.

**A09 — P2: URI com senha percent-encoded quebra a configuração do Alembic.**

Referência: [configuração do URL](/home/vini/dev/MH7/SPE/alembic/env.py:18).

Reprodução sem conexão: configurar `postgresql://user:p%40ss@localhost/db` com `set_main_option` lançou `ValueError: invalid interpolation syntax`. A interpolação do ConfigParser interpreta `%`. Esse mecanismo já existia na `main`; na migração para PostgreSQL, senhas com caracteres reservados tornam esse caso relevante para a implantação.

Correção: escapar `%` para a camada ConfigParser ou fornecer o URL diretamente à criação da engine, sem essa interpolação. Preservar a decodificação correta da senha pelo SQLAlchemy e testar migração online com uma senha contendo caracteres reservados. Não montar URIs por concatenação de credenciais sem codificação.

**A10 — P2: schema da API ainda permite nulo incompatível com o novo DDL.**

Referências: [UserUpdate.role](/home/vini/dev/MH7/SPE/app/features/users/user_schemas.py:124), [NOT NULL no banco](/home/vini/dev/MH7/SPE/alembic/versions/001_db_base.py:44).

Reprodução: `UserUpdate.model_validate({'role': None})` passou; a atualização real pelo repositório falhou em `NotNullViolation` na coluna `role`. O repositório usa `exclude_unset=True`, portanto um nulo explicitamente enviado é incluído. A proteção adicionada aos booleanos não cobre esse campo.

Correção: distinguir campo omitido de nulo explícito e rejeitar `role=null` na entrada, retornando erro de validação. Alinhar schemas, `nullable` dos models e DDL, examinando os demais campos obrigatórios. Testar pelo endpoint real; não depender de um IntegrityError como validação de entrada.

**A11 — P2: CI reproduz uma falha e não valida a execução nativa PostgreSQL.**

Referências: [teste com dependência do ambiente](/home/vini/dev/MH7/SPE/tests/features/system/test_backup_service.py:201), [preparação do CI](/home/vini/dev/MH7/SPE/.github/workflows/ci.yml:61), [fixture SQLite](/home/vini/dev/MH7/SPE/tests/conftest.py:146), [tracking desativado fora do PostgreSQL](/home/vini/dev/MH7/SPE/app/features/daily_summaries/daily_summary_events.py:277).

Com Python 3.12 e os valores de `.env.example` usados pelo CI, a suíte terminou com **1 falha e 1.042 testes passando**, cobertura indicada de 99%. O teste espera usuário `spe`, mas o exemplo configura `spe_user`. Foi sobrescrito apenas o URI para apontar ao banco isolado durante a auditoria; a falha usa os campos `POSTGRES_*` do exemplo.

Correção: tornar o teste independente do `.env`, fornecendo explicitamente suas configurações por fixture/monkeypatch. Adicionar um job com PostgreSQL 17 e migrações reais, cobrindo importação, backfill, fluxo da API, restore e os casos A01–A10. A alta cobertura atual, com SQLite e mocks, não comprova o comportamento dos eventos, FKs, tipos e exceções do PostgreSQL.

**A12 — P2: autogenerate interpreta tabelas existentes como removidas.**

Referência: [target_metadata do Alembic](/home/vini/dev/MH7/SPE/alembic/env.py:20).

`alembic check`, contra o banco atualizado na revisão `003`, detectou remoção das 15 tabelas da aplicação, incluindo `daily_summaries`, além de índices. O processo de migração importa `Base`, mas não registra os models antes de usar `Base.metadata`. O padrão já existia na `main`; continua perigoso para a manutenção desta migração. Nenhuma revisão destrutiva foi gerada ou aplicada na auditoria.

Correção: ter um registro explícito de todos os models carregado pelo Alembic, alinhar o metadata com o DDL PostgreSQL manual e definir o tratamento de índices/constraints intencionais que existam só no banco. Exigir `alembic check` sem operações destrutivas espúrias após `upgrade head`. Revisar toda revisão gerada antes de aplicá-la.

**Mudanças e condições de implantação que também precisam ser tratadas**

| Ponto | Providência |
| --- | --- |
| Logins e IDs da auditoria | O exportador e a revisão `003` removem `LOGIN` e reenumeram os demais IDs. Na cópia foram excluídos **875 logins**. É comportamento explícito da branch, não perda acidental encontrada pela comparação. Documentar a política e preservar a cópia original para consulta. |
| Rotas removidas | Comparação do OpenAPI da `main` e da branch: saem `POST /api/v1/sync/database` e `POST /api/v1/adjustments/admin/reprocess-daily-excess`; entra `POST /api/v1/daily-summaries/admin/reprocess`. Atualizar consumidores e observar a retirada de `overwrite_reviewed` do contrato anterior. |
| Fuso do banco | A revisão `001` fixa `America/Fortaleza`, enquanto a aplicação aceita `TIMEZONE` configurável. O fuso testado foi Fortaleza. Para suportar outro, unificar timezone das conexões, limites de data e datetimes sem offset; ou restringir explicitamente a configuração suportada. |
| Arquivos físicos | O pacote testado contém schema e dados, não todo o `UPLOAD_DIR`. Migrar e validar também anexos, firmwares, logos e Excels oficiais referenciados por caminhos. Banco restaurado não prova que esses arquivos existem. |
| Escritores durante a migração | O runbook precisa congelar API antiga, dispositivos, imports e rotinas que alterem a origem até o corte. Um snapshot consistente do SQLite não incorpora gravações posteriores. Fazer a paridade final antes de habilitar escritores no destino. |
| Banco novo e ordem | Executar `001/002 → importar → 003 → backfill → validar`, conforme o fluxo atual, em destino novo e explicitamente identificado. Evitar inicializar a API nova antes dessa etapa: o entrypoint aplica `head`, enquanto o fluxo SQLite espera importar em `002`. |
| Backfill e disponibilidade | O Alembic sozinho cria a tabela, mas não materializa o histórico. A API não deve receber tráfego enquanto os resumos necessários estiverem ausentes ou pendentes. O endpoint manual usa BackgroundTasks sem progresso persistido; não substitui a recuperação durável de A03. |
| Retorno à versão antiga | `001` e `003` não têm downgrade automático. Conservar SQLite e arquivos originais; ensaiar recuperação antes do corte. Depois de novas gravações no PostgreSQL, voltar ao SQLite antigo exige reconciliação dessas gravações, não apenas trocar a conexão. |

**Sequência proposta para a correção e nova validação**

1. Corrigir A01–A04 primeiro, com regressões em PostgreSQL real. Eles permitem restore indisponível, alteração de competência fechada e uso de totais inconsistentes.
2. Resolver A05–A12, incluindo precisão dos totais, configuração única de conexão, exceções do driver e CI. Se uma revisão já foi aplicada em algum ambiente, usar revisão corretiva; não apenas editar sua definição antiga.
3. Repetir a migração sobre uma cópia recente e representativa, incluindo expedientes fracionários e batidas editadas. Verificar dados, totais diários e mensais, status/aprovações, anexos e arquivos oficiais.
4. Ensaiar backup criptografado e restore com dados após uso normal da API, não somente imediatamente após a importação ordenada por ID. Verificar conteúdo e sequências, além de contagens.
5. Validar concorrência, reinício e falhas entre gravação, recálculo e fechamento; comprovar que não existe resumo obsoleto aceito como atual.
6. Ensaiar o corte completo em homologação, medir tempo de migração/backfill/restore, conferir readiness e executar os fluxos do frontend e dos dispositivos reais antes de abrir escrita em produção.

**Limites do parecer**

Não foram acessados ou alterados bancos de produção. A origem avaliada foi o `spe.db` local disponível. Não foram validados carga e volume de produção, failover/PITR, infraestrutura externa, entrega real de e-mail/Telegram, hardware biométrico/impressoras, todos os consumidores do frontend, nem equivalência visual completa de PDFs/Excels. Os testes positivos delimitam o que passou; não anulam as reproduções de falha nem constituem garantia de ausência de outros defeitos.

As reproduções sanitizadas e resultados agregados estão em [evidencias.json](/home/vini/dev/MH7/SPE/audits/2026-10-16-postgresql/evidencias.json). Não foram incluídos dumps, credenciais reais, dados biométricos ou dados pessoais nesse artefato.
