**Correções da auditoria PostgreSQL — 16/10/2026**

Os 12 achados do relatório original foram tratados no código, nos testes e no procedimento de implantação. Durante a validação adicional foi encontrada e corrigida uma falha no exportador PostgreSQL em Python. A revisão nova é a 004. As revisões 001 e 003 foram preservadas.

Os testes usaram Python 3.12.13, dependências travadas e PostgreSQL 17.11 em ambiente exclusivo, acessível apenas pelo endereço local. Nenhuma alteração foi aplicada à produção ou ao PostgreSQL de desenvolvimento já existente. O SQLite disponível foi acessado para leitura e sua cópia foi migrada para bancos descartáveis.

**Correções por achado**

| Achado | Correção aplicada | Verificação |
| --- | --- | --- |
| A01: restore de batidas editadas | A revisão 004 torna a FK da batida original DEFERRABLE INITIALLY DEFERRED. O modelo acompanha o schema. | Restore real com filho 101 antes do pai 100 e verificação da FK adiada; backup completo restaurado em outro banco. |
| A02: competência incorreta em UTC | Criação e edição administrativas normalizam o instante para America/Fortaleza antes das validações por data. | Entrada UTC na virada do mês recebe HTTP 400 quando pertence ao mês local fechado; os dois schemas são verificados. |
| A03: resumo antigo após falha | O resumo e a alteração de origem são calculados e gravados na mesma transação, antes do commit. A gravação deixou de depender de tarefas em memória após o commit. | Falha controlada desfaz as batidas e mantém o resumo anterior; uma nova transação conclui as oito horas corretamente. |
| A04: corrida no fechamento | Escritores obtêm lock compartilhado da competência antes de gravar. Fechamento e reabertura usam lock exclusivo; a competência é revalidada sob essa proteção. O relatório, o fechamento e sua auditoria permanecem na transação protegida. Os resumos usam lock por usuário/data. | Fechar primeiro impede a gravação posterior; gravar primeiro faz o fechamento esperar e exportar 480 minutos. Dois escritores simultâneos do mesmo dia preservam as quatro batidas e o total correto. |
| A05: perda por arredondamento diário | As sete durações materializadas passam para NUMERIC(14,6). A agregação preserva frações de minuto e converte o valor numérico corretamente para os cálculos dos relatórios. | Dez dias de expediente de 8,08 horas mantêm 4.848 minutos, iguais ao cálculo legado. |
| A06: destinos de backup divergentes | API, scripts de importação e verificação e backup usam SQLALCHEMY_DATABASE_URI como fonte de verdade. URI inválido gera falha explícita. O Compose de desenvolvimento também usa a porta interna correta. | Teste com variáveis POSTGRES conflitantes mantém o host, a porta e o banco do URI. Senha codificada é decodificada corretamente. |
| A07: constraint do driver errado | A identificação de constraint percorre o adaptador SQLAlchemy e a causa asyncpg, além de aceitar psycopg2. A falha do fechamento remove o arquivo produzido por aquela operação. | Violação real do índice único retorna o nome esperado pelo tratamento de domínio; testes do fechamento continuam passando. |
| A08: texto confundido com comando psql | Um leitor mantém o estado de strings, identificadores, comentários e dollar quotes. Apenas diretivas fora desses valores são filtradas ou rejeitadas. A limpeza de arquivos é atômica. | Restore e backup criptografado preservam textos multilinha com barras invertidas, restrict, unrestrict e network-path. |
| A09: senha com percentual no Alembic | O URI é escapado para a interpolação do ConfigParser; a introspecção de schema usa URL estruturado. | Conexão online do Alembic com usuário temporário e senha sintética contendo arroba, percentual e dois-pontos. |
| A10: nulo incompatível com o DDL | A atualização de usuário rejeita username e role explicitamente nulos, mantendo campos omitidos válidos. Os flags obrigatórios seguem a mesma regra. | Validação dos schemas e suíte da funcionalidade de usuários. |
| A11: CI sem PostgreSQL real | Job separado provisiona PostgreSQL 17 e executa os testes de integração com credenciais explícitas. Cada teste cria e remove somente seu próprio banco temporário. | Os 11 testes de integração passaram localmente contra PostgreSQL real. O job remoto ainda será executado pelo CI. |
| A12: metadata vazia ou divergente | Alembic carrega todos os modelos; FKs, nulabilidade, tipos, checks e índices refletem as migrações manuais. TEXT e strings sem limite equivalentes não geram alteração artificial. | Alembic check não encontrou novas operações de upgrade no banco migrado. |
| Adicional: exportador Python | O cursor nomeado lê o primeiro lote antes de acessar a descrição das colunas. Antes disso, description era None e a exportação retornava falha. | Exportação real, compactação, criptografia, descriptografia e restauração dos dados sintéticos com resumo diário. |

**Resultados finais**

| Ensaio | Resultado |
| --- | --- |
| Suíte completa | 1.066 testes aprovados em 18,79 segundos; cobertura global reportada de 99%. |
| PostgreSQL real | 11 testes aprovados; migração nova, atomicidade, concorrência, fuso, precisão, restore, senha e metadata. |
| Migração da cópia SQLite | Revisões 001/002, importação, upgrade para 003/004 e backfill concluídos. |
| Paridade célula a célula | 5.550 linhas esperadas, zero divergências, considerando a remoção intencional dos logins. |
| Backfill | 4.046 resumos para 14 usuários, de janeiro a 16/10/2026. |
| Relatórios | 280 comparações entre cálculo legado e materializado, zero divergências. |
| Backup por snapshot | Estrutura e dados da mesma fotografia, pacote criptografado e restore: 15 tabelas e 9.596 linhas com checksums idênticos. |
| Sequências do banco restaurado | As 15 sequências têm próximo ID maior que o máximo existente. |
| Integridade do schema | Alembic check sem operações novas; FK original adiável e adiada. |
| Análise estática | Compilação de app, scripts e Alembic; Ruff F nos arquivos Python alterados; ty nos quatro helpers novos de conexão, erros, locks e SQL. |

**Decisões mantidas**

O PostgreSQL de produção será externo ao Compose. Os alvos de banco do Makefile não iniciam containers automaticamente. O Compose continua disponível para desenvolvimento. A remoção dos registros de login e das rotas já removidas é intencional e foi mantida. Os arquivos físicos serão transferidos manualmente. O fuso é America/Fortaleza e a migração ocorrerá sem novas gravações. As revisões 001 e 003 continuam sem downgrade automático.

Não foram adicionados comentários ou docstrings ao código Python corrigido. Os comentários explicativos de comandos ficam no Makefile; os procedimentos e as evidências ficam na documentação.

**Aplicação**

Para migrar a origem SQLite para um PostgreSQL novo, configure o URI, o fuso e a SECRET_KEY original, instale o cliente pg_dump compatível e siga scripts/README.md. O comando make db-migrate-all prepara a revisão 002 para a importação, aplica 003/004, verifica a paridade e faz o backfill. Só inicie a API após concluir essas etapas e a transferência manual dos arquivos.

Se um PostgreSQL já estiver na revisão 003, com a API parada, execute:

    make upgrade
    .venv/bin/python -m scripts.backfill_daily_summaries --execute
    .venv/bin/python -m alembic check

O backfill é necessário para recompor as durações que tinham sido arredondadas nos resumos anteriores. Ele também processa períodos fechados, preservando as batidas e os ajustes de origem.

Os ensaios cobrem a cópia e os cenários documentados. O ambiente externo de produção e sua capacidade sob carga não foram acessados ou validados; os resultados não são uma garantia de ausência de qualquer falha futura.

**Commits do código**

- 75a4153: destino de conexão, preservação dos valores SQL e exportador de backup.
- 8ba078c: apuração e fechamento transacionais, precisão, migração 004 e metadata.
- 66ca01b: fuso das entradas administrativas e campos obrigatórios.
- 3483cdb: integração PostgreSQL real e job de CI.
- f0e06ab: comandos de banco e documentação para PostgreSQL externo em produção.
