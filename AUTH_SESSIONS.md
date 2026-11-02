# Sessões renováveis e redefinição obrigatória

Implementação em `feature/refresh-token` no repositório SPE. As regras de autenticação ficam em `AuthService`; os routers recebem dados validados e delegam. O repositório concentra consultas e bloqueios. A auditoria individual dos contratos está em `ENDPOINT_AUDIT.md`.

## Contrato

- `POST /api/v1/auth/login`: preserva formulário username/password e acrescenta `expires_in`, `refresh_token`, `refresh_expires_in` e `password_change_required` à resposta.
- `POST /api/v1/auth/refresh`: JSON `{"refresh_token":"..."}`; troca o par de tokens e invalida o refresh anterior.
- `POST /api/v1/auth/logout`: mesmo corpo; encerra a família da sessão, inclusive seus access tokens. Resposta 204, inclusive para token desconhecido.
- `POST /api/v1/auth/password`: bearer da sessão e JSON `{"current_password":"...","new_password":"..."}`; valida senha atual e política compartilhada, impede repetição da senha, redefine a senha, limpa a exigência e devolve uma nova sessão.
- `GET /api/v1/auth/me`: permite ler o perfil durante a redefinição; as demais funcionalidades ficam bloqueadas.
- `POST /api/v1/users/` e `PUT /api/v1/users/{id}`: gestores e mantenedores podem definir `password_change_required`, respeitando as restrições de gestão de usuários existentes. O perfil próprio não permite alterar essa flag.

Quando a flag estiver ativa, o login emite exclusivamente um bearer curto com finalidade `password_change`, sem refresh. A aplicação direciona para uma tela obrigatória, com saída de sessão disponível. A mudança de senha invalida versões anteriores de autenticação. Tokens de uma sessão encerrada são rejeitados pelo backend.

## Segurança e concorrência

BFRI após isolamento em serviço/repositório: arquitetura 5, testabilidade 5, complexidade 2, risco de dados 2, risco operacional 3; resultado 3. Os controles adicionais são testes de integração e concorrência, migração aditiva e revogação transacional.

Refresh tokens são opacos, aleatórios e persistidos somente como SHA-256. Cada rotação preserva a família e seu prazo absoluto. Reutilizar um refresh consumido revoga toda a família; nenhum nó depende de memória local para essa decisão. Bloqueio da linha do usuário serializa rotação, logout e redefinição. O Flutter coordena requisições simultâneas para compartilhar uma renovação e limita a repetição da chamada original.

O índice único do hash atende à busca do refresh; índices de família e usuário atendem revogação. O índice parcial de sessão ativa atende à verificação de access tokens, sem varrer o histórico de rotações. O índice de expiração atende à remoção de até 1.000 registros por execução a cada dez minutos. A remoção usa SKIP LOCKED e só elimina famílias cujo prazo absoluto expirou, preservando detecção de replay até esse prazo.

A segurança de refresh segue a rotação com detecção de replay da [RFC 9700, seção 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14). As respostas de autenticação impedem cache. As senhas continuam usando o hashing da aplicação fora do loop assíncrono. O aplicativo guarda os tokens no armazenamento seguro existente e lembra somente o nome de usuário, eliminando persistência da senha em texto puro.

## Implantação e reversão

1. Fazer backup e validar a migração em homologação, usando a mesma versão de PostgreSQL da produção.
2. Aplicar `uv run alembic upgrade head`: a revisão 009 adiciona a flag com valor false e a tabela de refresh tokens. Nenhum usuário existente é obrigado a redefinir a senha automaticamente.
3. Publicar o backend. Configurações novas: `REFRESH_TOKEN_EXPIRE_DAYS=30` e `PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES=10`. Recomenda-se `ACCESS_TOKEN_EXPIRE_MINUTES=15`; o valor existente foi preservado para não alterar sessões implicitamente.
4. Publicar o Flutter e validar login, renovação, logout e redefinição em celular, tablet e desktop. Só então começar a exigir redefinição dos usuários.
5. Manter os adaptadores de endpoints antigos enquanto houver clientes anteriores. Eles aparecem depreciados no OpenAPI, mas continuam funcionando.
6. Monitorar 401/403 por rota, falhas do job `expired_refresh_tokens`, crescimento de `refresh_tokens` e latência de login/refresh. Aplicar limites de requisição no ingresso compartilhado para login, refresh e troca de senha; o repositório não tinha infraestrutura de limitação distribuída e esta entrega não a provisiona.

Na reversão, suspender primeiro a ativação de novas exigências. Reverter os aplicativos mantendo a migração aditiva enquanto houver sessões da versão nova. Um backend antigo não aplica a exigência de redefinição, portanto reverter o backend exige avaliar essa perda de proteção. O downgrade 009 remove somente a tabela de tokens e a flag e encerra a renovação de todas as sessões. Não executar downgrade durante tráfego da versão nova.

A validação PostgreSQL usa bancos temporários criados pelo fixture, com prefixo `spe_test_`, em servidor descartável. Nenhuma migração ou consulta de teste foi executada na produção.
