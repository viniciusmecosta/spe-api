# Autenticação, sessões e redefinição obrigatória de senha

[![PyJWT](https://img.shields.io/badge/PyJWT-2.13%2B-000000?logo=jsonwebtokens)](https://pyjwt.readthedocs.io/) [![bcrypt](https://img.shields.io/badge/bcrypt-5.0%2B-4B8BBE)](https://pypi.org/project/bcrypt/) [![FastAPI](https://img.shields.io/badge/FastAPI-OAuth2-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)](https://www.sqlalchemy.org/) [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

Funcionamento do login, renovação de sessão com refresh token, exigência de troca de senha e autenticação dos coletores físicos no SPE. A tabela completa de rotas está em [`endpoints.md`](endpoints.md) e as variáveis de tempo de expiração estão em [`configuracao-e-limites.md`](configuracao-e-limites.md).

## Bibliotecas utilizadas

- `pyjwt`: assinatura e leitura dos tokens JWT (`HS256`) com as claims `sub`, `ver`, `jti`, `scope` e `exp`.
- `bcrypt`: hash e verificação de senhas de usuários e das chaves de API dos coletores.
- `fastapi.security`: leitura do formulário `OAuth2PasswordRequestForm` no controller de login e extração do header `Authorization: Bearer`.
- `hashlib` e `secrets` (biblioteca padrão): geração do refresh token (`secrets.token_urlsafe`) e cálculo do hash `SHA-256` salvo no banco.
- `sqlalchemy` e `asyncpg`: persistência na tabela `refresh_tokens` com lock de linha (`SELECT ... FOR UPDATE`).

## Login e emissão de tokens

O controller [`auth_router.py`](../app/features/auth/auth_router.py) expõe `POST /api/v1/auth/login` recebendo `username` e `password` (`application/x-www-form-urlencoded`) e aplica os headers `Cache-Control: no-store` e `Pragma: no-cache` em todas as respostas. O [`AuthService`](../app/features/auth/auth_service.py) confere se o usuário está ativo e valida a senha com o hash `bcrypt` salvo em `users.hashed_password`.

A resposta do login depende da flag `users.password_change_required`:

1. Usuário sem pendência de troca de senha (`password_change_required = false`):
   - Gera um `access_token` JWT com `scope="access"`, `ver=user.auth_version`, `jti` único e expiração configurada em `ACCESS_TOKEN_EXPIRE_MINUTES` (padrão 30 minutos).
   - Gera um `refresh_token` opaco, grava apenas o hash `SHA-256` dele na tabela `refresh_tokens` associado a um `family_id` e define `expires_at` conforme `REFRESH_TOKEN_EXPIRE_DAYS` (padrão 30 dias).
   - Retorna `password_change_required: false`, `access_token`, `expires_in`, `refresh_token` e `refresh_expires_in`.

2. Usuário com troca de senha obrigatória (`password_change_required = true`):
   - Gera apenas um `access_token` restrito com `scope="password_change"` e validade curta definida por `PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES` (padrão 10 minutos).
   - Não gera `refresh_token` (`null`) e retorna `password_change_required: true`.

## Rotação de refresh token e revogação por família

A renovação da sessão é feita em `POST /api/v1/auth/refresh` (RFC 9700 seção 4.14):

1. O cliente envia `{"refresh_token": "<token>"}`.
2. O [`AuthService`](../app/features/auth/auth_service.py) e o [`AuthRepository`](../app/features/auth/auth_repository.py) calculam o `SHA-256` do token recebido e buscam o registro em `refresh_tokens` com `FOR UPDATE`.
3. Se o token já tiver sido usado ou revogado (`revoked_at` preenchido ou `replaced_by_id` apontando para outro token), o sistema identifica reutilização indevida, revoga todos os tokens ativos do mesmo `family_id`, comita a revogação e retorna `401 Unauthorized`.
4. Se o token estiver vencido, o usuário estiver inativo ou `password_change_required` tiver sido marcado para o usuário, a família inteira também é revogada.
5. Se o token estiver válido, o registro atual recebe `revoked_at`, um novo refresh token é criado na mesma família (`family_id`), `replaced_by_id` aponta para o novo registro e a API devolve um novo par `access_token` + `refresh_token`.

No logout (`POST /api/v1/auth/logout`), o service revoga todos os tokens da família (`family_id`) correspondente ao refresh token enviado e retorna `204 No Content`.

## Redefinição obrigatória de senha

Gestores e mantenedores podem marcar `password_change_required: true` ao cadastrar (`POST /api/v1/users/`) ou editar um funcionário (`PUT /api/v1/users/{user_id}`), ou ao redefinir a senha de outro usuário. Sempre que isso ocorre, o service incrementa `users.auth_version` e revoga todas as sessões ativas daquele usuário.

Enquanto `password_change_required` estiver ativo:

- A dependência [`get_current_user`](../app/shared/deps.py) bloqueia chamadas aos demais controllers da API com `403 Forbidden` e `code: "password_change_required"`.
- Apenas as rotas que usam [`get_password_change_user`](../app/shared/deps.py) aceitam o token com `scope="password_change"`: `GET /api/v1/auth/me` e `POST /api/v1/auth/password`.
- Em `POST /api/v1/auth/password`, o usuário envia `current_password` e `new_password` (mínimo de 8 caracteres, com maiúscula, minúscula, número e diferente da senha atual).
- O service valida a senha atual, grava o novo hash `bcrypt`, muda `password_change_required` para `false`, incrementa `auth_version`, revoga sessões antigas, registra `CHANGE_OWN_PASSWORD` na auditoria e já retorna um novo par `access_token` + `refresh_token` liberado para uso normal.

## Perfis de usuário e autenticação dos coletores

As dependências em [`app/shared/deps.py`](../app/shared/deps.py) controlam o nível de acesso em cada controller:

- `EMPLOYEE`: registra o próprio ponto, consulta seus espelhos, comprovantes, saldos e abre solicitações de ajuste.
- `MANAGER`: possui as permissões de funcionário e gerencia usuários, expedientes, feriados, aprovação/rejeição de ajustes, fechamento de folha e relatórios da equipe.
- `MAINTAINER`: possui as permissões de gestor e gerencia dados da empresa, credenciais de coletores, firmwares OTA, reprocessamento de apurações, reversão de status de ajustes, logs de rotina e disparo manual de jobs.

Os coletores biométricos ESP32 autenticam via header `X-Device-API-Key` no formato `<device_id>:<secret>`, validado por `verify_device_api_key` contra o hash salvo na tabela `device_credentials`.
