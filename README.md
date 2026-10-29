# SPE - Sistema de Ponto Eletrônico

## Sobre o Projeto

O **SPE** é uma API backend responsável pela centralização e automação do controle de assiduidade de colaboradores. A
solução gerencia registros de ponto, definição de jornadas de trabalho, tratamento de justificativas, consolidação de
horas trabalhadas e execução do fechamento mensal.

A aplicação foi projetada com foco em confiabilidade, organização em camadas e facilidade de evolução, permitindo sua
integração com sistemas de recursos humanos, dispositivos de coleta de ponto e ferramentas de análise gerencial.

## Stack Tecnológica

* **Linguagem:** Python 3.12
* **Framework Web:** FastAPI
* **Persistência:** PostgreSQL 17
* **ORM:** SQLAlchemy
* **Versionamento de esquema:** Alembic
* **Autenticação e Segurança:** JWT com versão de sessão e hash de senhas com Bcrypt
* **Processamento assíncrono e rotinas:** APScheduler e fila durável no PostgreSQL
* **Geração de relatórios:** OpenPyXL

## Configuração do Ambiente

A aplicação utiliza variáveis de ambiente para controle de comportamento e proteção de dados sensíveis. Antes da
execução, crie um arquivo `.env` na raiz do projeto, podendo utilizar o `.env.example` como referência.

### Configurações Gerais

* **`PROJECT_NAME`**
  Nome descritivo da aplicação.

* **`TIMEZONE`**
  Fuso horário utilizado na interpretação e validação temporal dos registros: `America/Fortaleza`.

* **`UPLOAD_DIR`**
  Diretório destinado ao armazenamento de arquivos enviados ou gerados pelo sistema.

* **`EXCLUDED_EMPLOYEE_IDS`**
  Lista de identificadores de colaboradores que devem ser ignorados por regras automatizadas.

### Banco de Dados

* **`SQLALCHEMY_DATABASE_URI`**
  String de conexão PostgreSQL utilizada pela API, pelos backups e pelos scripts:
  `postgresql+asyncpg://usuario:senha@host:5432/spe`.
  Codifique os caracteres reservados da senha no URI.

Em produção, utilize o PostgreSQL externo já provisionado. O banco não depende do
Docker Compose. Instale um cliente `pg_dump` compatível com o servidor na máquina da API e
garanta que a conta do serviço NSSM consiga executá-lo. Consulte o [procedimento de migração e restauração](scripts/README.md)
antes de inicializar a aplicação. Durante a migração, suspenda as gravações, conclua o
backfill e migre os arquivos físicos manualmente antes de liberar o acesso.

### Segurança e Autenticação

* **`SECRET_KEY`**
  Chave criptográfica utilizada na assinatura de tokens JWT.

* **`ALGORITHM`**
  Algoritmo de assinatura dos tokens.

* **`ACCESS_TOKEN_EXPIRE_MINUTES`**
  Tempo de expiração do token de acesso.

* **`DEVICE_API_KEY`**
  Chave estática para autenticação de dispositivos ou integrações externas responsáveis pelo envio de dados.

### Usuário Administrador Inicial

* **`FIRST_SUPERUSER`**
  Identificador do usuário administrador criado na primeira inicialização.

* **`FIRST_SUPERUSER_PASSWORD`**
  Credencial inicial do usuário administrador.

### Implantação no Windows com NSSM

A produção usa PostgreSQL nativo e NSSM, sem Docker. O [guia de banco e operação](scripts/README.md)
detalha a migração, restauração, atualização e retomada das rotinas. A revisão atual do schema é `008`.
Na migração do SQLite, importe os dados com o PostgreSQL na revisão `002` antes de avançar para `head`;
na atualização de PostgreSQL já implantado, aplique as revisões pendentes com a API parada.

Preserve o `.env`, a `SECRET_KEY`, os arquivos físicos e a configuração do NSSM. O backup do banco não inclui
`uploads/`, inclusive os anexos pendentes em `.delivery_queue/`. Confira o PATH do `pg_dump`, as permissões da
conta do serviço, o diretório de trabalho, um único worker sem `--reload` e a inicialização do PostgreSQL antes da API.
Sincronize as dependências com `uv sync --locked --no-dev --no-build` usando o Python da instalação validada.

Use `/api/v1/health` para verificar o processo e `/api/v1/ready` para banco e schema. O mantenedor acompanha
rotinas, entregas e reprocessamentos em Admin > Monitoramento (`/api/v1/operations`). Durante a validação
inicial ou recuperação, `BACKGROUND_JOBS_ENABLED=false` pausa o consumidor; o agendador ainda pode registrar tarefas.
Confira pendências e destinatários antes de reativar o consumidor e reiniciar o NSSM para carregar a configuração.

Preserve o CORS que atende à rede local. Distribua o Flutter compatível com a renovação de sessão após alteração
de senha e os avisos de exportação parcial. Nos clientes da rede, configure o IP do servidor, não `127.0.0.1`.

### Configurações de E-mail

* **`SMTP_HOST`**
  Servidor SMTP utilizado para envio de mensagens.

* **`SMTP_PORT`**
  Porta de comunicação com o servidor SMTP.

* **`SMTP_USER`**
  Credencial de autenticação SMTP.

* **`SMTP_PASSWORD`**
  Senha ou token de aplicação associado ao usuário SMTP.

* **`EMAIL_FROM`**
  Endereço remetente das notificações do sistema.

Os relatórios e backups por e-mail são destinados aos mantenedores ativos com e-mail cadastrado.
Não há variável `EMAIL_TO` na configuração atual. Dados e logo da empresa vêm do cadastro; versão, ambiente e
fuso vêm de `APP_VERSION`, `ENVIRONMENT` e `TIMEZONE`.

## Desenvolvimento local com Docker Compose

O Docker Compose é uma alternativa para desenvolvimento local. A implantação de produção usa NSSM e PostgreSQL nativo.

Após configurar o arquivo `.env`, execute:

```bash
docker compose build
```

Em seguida, inicialize os serviços:

```bash
docker compose up -d
```

No ambiente local, o processo de bootstrap executa automaticamente:

* Aplicação das migrações estruturais
* Provisionamento do usuário administrador inicial
* Inicialização do servidor na porta 8000

A documentação interativa da API estará disponível em:

```
http://localhost:8000/docs
```

Para encerrar a execução:

```bash
docker compose down
```

## Estrutura do Projeto

O projeto adota organização em camadas, promovendo separação de responsabilidades e melhor manutenibilidade.

* **`/app/features/`**
  Funcionalidades com rotas HTTP, serviços, schemas, modelos e repositórios do domínio.

* **`/app/core/`**
  Configuração, segurança, inicialização, logs e tratamento de erros.

* **`/app/database/`**
  Engines, sessões, conexões e unidade de trabalho transacional.

* **`/app/shared/`**
  Dependências, validações e componentes compartilhados.

* **`/app/middleware/`**
  Logs de requisição e contexto de identificação disponível em `X-Request-ID`.

* **`/alembic/`**
  Histórico de migrações do schema PostgreSQL.

* **`/scripts/`**
  Importação SQLite, verificação de paridade, backfill e ensaio de restauração.

## Rotinas e arquivos

A cron verifica a necessidade das rotinas a cada dez minutos; o consumidor consulta a fila durável a cada cinco
segundos. `routine_logs` mantém resultados e períodos já entregues, e `background_jobs` guarda pendências,
tentativas, partes e progresso. Um `job_id` confirma registro da tarefa, não conclusão do envio.

Falhas confirmadas podem ser retomadas no Admin sem reenviar partes concluídas. Uma entrega `UNCERTAIN` exige
conferência no destino; a versão atual não oferece confirmação de recebimento ou reenvio autorizado no painel.
Os anexos pendentes devem sobreviver a reinícios. Confira a fila após restaurar um backup antes de liberar o consumidor.

Relatórios e anexos privados usam downloads autenticados; não publique `uploads/` inteiro como arquivos estáticos.
Os novos Excel são ordenados pelo nome dos funcionários; os históricos são preservados. ZIPs de espelhos podem
ter resultado parcial com manifesto; quando nenhum PDF é gerado, a resposta é `503`.

Os horários dos logs são formatados no fuso `TIMEZONE=America/Fortaleza`, independentemente do fuso do sistema ou container. O log comum não exibe `request_id`; o cabeçalho HTTP continua disponível para identificação da requisição.
