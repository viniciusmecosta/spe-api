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
* **Autenticação e Segurança:** JWT e hash de senhas com Passlib (Bcrypt)
* **Processamento assíncrono e rotinas:** APScheduler
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
Docker Compose. Instale um cliente `pg_dump` compatível com o servidor na máquina ou
container que executa a API. Consulte o [procedimento de migração e restauração](scripts/README.md)
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

* **`EMAIL_TO`**
  Destinatário principal dos relatórios operacionais e backups automatizados.

## Desenvolvimento local com Docker Compose

A aplicação está containerizada, garantindo padronização de ambiente e simplificação do processo de implantação.

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

* **`/app/api/`**
  Camada de exposição HTTP, responsável pelo roteamento e tratamento das requisições.

* **`/app/core/`**
  Configurações globais, segurança, carregamento de ambiente e dependências transversais.

* **`/app/database/`**
  Inicialização da engine, sessão e infraestrutura de persistência.

* **`/app/domain/models/`**
  Entidades ORM que representam o modelo de dados do sistema.

* **`/app/repositories/`**
  Abstração de acesso a dados, contendo operações de persistência.

* **`/app/schemas/`**
  Modelos de validação e serialização utilizados na comunicação da API.

* **`/app/services/`**
  Implementação das regras de negócio, cálculos operacionais e fluxos do domínio.

* **`/alembic/`**
  Histórico de versionamento do esquema do banco de dados.
