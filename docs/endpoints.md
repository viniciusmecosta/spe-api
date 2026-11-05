# Endpoints da API (`/api/v1`)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.141%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Pydantic](https://img.shields.io/badge/Pydantic-2.13%2B-E92063)](https://docs.pydantic.dev/) [![OpenAPI](https://img.shields.io/badge/OpenAPI-3.1-6BA539?logo=openapiinitiative&logoColor=white)](https://spec.openapis.org/oas/v3.1.0) [![Granian](https://img.shields.io/badge/Granian-2.8%2B-5A4FCF)](https://github.com/emmett-framework/granian) [![RFC 9457](https://img.shields.io/badge/Erros-RFC_9457-0052CC)](https://www.rfc-editor.org/rfc/rfc9457.html)

Lista de todos os endpoints registrados pelos controllers do SPE em [`app/router.py`](../app/router.py). O schema OpenAPI 3.1 fica em `/api/v1/openapi.json` e o Swagger UI em `/docs`.

## Bibliotecas utilizadas nos controllers

- `fastapi` e `starlette`: definição dos controllers (`APIRouter`), injeção de dependências (`Depends`), download de arquivos e middlewares ASGI.
- `pydantic` e `email-validator`: validação dos schemas de body e query (`Month`, `Year`, `PageOffset`, `PageLimit`) e serialização das respostas.
- `python-multipart`: leitura de formulários OAuth2 e uploads `multipart/form-data` (logos, atestados, relatórios legados e firmwares).
- `granian`: servidor HTTP/ASGI em Rust que executa a aplicação.

## Formato padrão de erros

Qualquer erro HTTP, falha de validação ou `DomainException` passa por [`app/core/exceptions.py`](../app/core/exceptions.py) e retorna no formato RFC 9457 Problem Details com o header `X-Request-ID`:

```json
{
  "type": "https://api.spe.com/erros/requisicao-invalida",
  "title": "Requisição Inválida",
  "status": 400,
  "detail": "Motivo do erro.",
  "instance": "/api/v1/time-records"
}
```

Quando ocorre erro de validação do Pydantic (`422 Unprocessable Content`), o JSON traz também o campo `invalid_params` indicando o campo (`loc`), a mensagem traduzida (`msg`) e o tipo (`type`).

## 1. Healthcheck e operações (`/api/v1`)

Controller: [`app/features/system/monitoring.py`](../app/features/system/monitoring.py) e [`app/router.py`](../app/router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health` | Público | Retorna `status: "ok"`, nome da aplicação e versão (`APP_VERSION`). |
| `GET` | `/api/v1/ready` | Público | Checa conexão com o PostgreSQL, fila de jobs e serviço de horário. |
| `GET` | `/api/v1/operations` | `MAINTAINER` | Retorna contadores da fila `background_jobs`, status do banco e últimas rotinas. |
| `POST` | `/api/v1/operations/jobs` | `MAINTAINER` | Enfileira manualmente `audit_open_records`, `send_daily_reports` ou `sync_holidays` (`202 Accepted`). |

## 2. Autenticação (`/api/v1/auth`)

Controller: [`app/features/auth/auth_router.py`](../app/features/auth/auth_router.py). Detalhes em [`autenticacao.md`](autenticacao.md).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Público | Valida `username` e `password` via form OAuth2 e emite os tokens da sessão. |
| `GET` | `/api/v1/auth/me` | Autenticado (inclusive `password_change`) | Retorna os dados do usuário dono do token atual. |
| `POST` | `/api/v1/auth/refresh` | Público (com `refresh_token`) | Rotaciona o refresh token e revoga a família inteira se detectar reutilização. |
| `POST` | `/api/v1/auth/logout` | Público (com `refresh_token`) | Revoga a família do refresh token informado (`204 No Content`). |
| `POST` | `/api/v1/auth/password` | Autenticado (inclusive `password_change`) | Troca a senha do próprio usuário, desmarca `password_change_required`, incrementa `auth_version` e devolve nova sessão. |

## 3. Usuários (`/api/v1/users`)

Controller: [`app/features/users/user_router.py`](../app/features/users/user_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/users/` | `MANAGER` | Lista usuários com paginação (`after_id`, `limit`), busca (`search`), filtro por `is_active` e `role`, e ordenação (`id`, `name`, `username`, `created_at`, `updated_at`). |
| `POST` | `/api/v1/users/` | `MANAGER` | Cadastra usuário com perfil, expediente opcional e flag `password_change_required`. |
| `GET` | `/api/v1/users/me` | `EMPLOYEE` | Retorna os dados do próprio usuário logado. |
| `PUT` | `/api/v1/users/me` | `EMPLOYEE` | Atualiza dados cadastrais permitidos ao próprio usuário. |
| `GET` | `/api/v1/users/{user_id}` | `EMPLOYEE` (próprio) / `MANAGER` | Busca um usuário pelo ID. |
| `PUT` | `/api/v1/users/{user_id}` | `MANAGER` | Atualiza cadastro, status ativo, perfil, senha, biometria e `password_change_required`. |

## 4. Expedientes (`/api/v1/schedules`)

Controller: [`app/features/users/work_schedule_router.py`](../app/features/users/work_schedule_router.py). Guarda a jornada diária em minutos (`daily_minutes`, 0 a 1440) e grava o resumo compactado na auditoria.

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/schedules/bulk` | `MANAGER` | Lista os grupos de expediente vigentes no `month` e `year` informados. |
| `GET` | `/api/v1/schedules/bulk/{valid_from}/{valid_until}` | `MANAGER` | Busca os funcionários e horários de uma vigência específica. |
| `POST` | `/api/v1/schedules/bulk` | `MANAGER` | Cria um expediente em lote para os funcionários selecionados. |
| `PUT` | `/api/v1/schedules/bulk/{valid_from}/{valid_until}` | `MANAGER` | Edita datas de vigência, funcionários vinculados e minutos diários do expediente em lote. |
| `DELETE` | `/api/v1/schedules/bulk/{valid_from}/{valid_until}` | `MANAGER` | Exclui um expediente em lote pelo período de vigência. |

## 5. Registro de ponto e comprovantes (`/api/v1/time-records`)

Controller: [`app/features/time_records/time_record_router.py`](../app/features/time_records/time_record_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `POST` | `/api/v1/time-records` | `EMPLOYEE` / `MANAGER` | Registra batida do próprio funcionário (`ManualTimeRecordCreate`) ou batida lançada por gestor para outro funcionário (`AdministrativeTimeRecordCreate`). |
| `GET` | `/api/v1/time-records` | `EMPLOYEE` / `MANAGER` | Lista batidas filtradas por `scope` (`mine` ou `team`), `user_id`, `record_date`, `start_date`, `end_date`, `month`, `year`, `skip` e `limit`. |
| `POST` | `/api/v1/time-records/{id}/type-transitions` | `EMPLOYEE` / `MANAGER` | Alterna o tipo da batida (`ENTRY` / `EXIT`) quando válido na sequência do dia e recalcula o resumo diário. |
| `PATCH` | `/api/v1/time-records/{record_id}` | `MANAGER` | Altera horário ou tipo de uma batida com justificativa obrigatória. |
| `DELETE` | `/api/v1/time-records/{record_id}` | `MANAGER` | Exclui logicamente uma batida exigindo `justification` (5 a 300 caracteres). |
| `GET` | `/api/v1/time-records/{id}/timeline` | `MAINTAINER` | Mostra todo o histórico de edições de uma batida. |
| `GET` | `/api/v1/time-records/receipt/{short_id}` | `EMPLOYEE` (próprio) / `MANAGER` | Consulta os dados do comprovante de ponto pelo `short_id` (Hashids). |
| `GET` | `/api/v1/time-records/receipt/{short_id}/pdf` | `EMPLOYEE` (próprio) / `MANAGER` | Baixa o comprovante de registro de ponto em PDF. |

## 6. Ajustes e abonos (`/api/v1/adjustments`)

Controller: [`app/features/adjustments/adjustment_router.py`](../app/features/adjustments/adjustment_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `POST` | `/api/v1/adjustments/` | `EMPLOYEE` | Abre uma solicitação de ajuste de ponto para uma data. |
| `POST` | `/api/v1/adjustments/admin/waive` | `MANAGER` | Lança abono administrativo para um funcionário. |
| `POST` | `/api/v1/adjustments/{id}/attachments` | `EMPLOYEE` (autor) / `MANAGER` | Envia anexo (atestado ou comprovante) para a solicitação de ajuste. |
| `GET` | `/api/v1/adjustments/{id}/download` | `EMPLOYEE` (autor) / `MANAGER` | Baixa o anexo da solicitação de ajuste. |
| `GET` | `/api/v1/adjustments` | `EMPLOYEE` / `MANAGER` | Lista ajustes filtrando por `scope` (`mine` ou `team`), `month`, `year`, `status` (`PENDING`, `APPROVED`, `REJECTED`, `NOT_PENDING`), `order_by` e `order_direction`. |
| `PUT` | `/api/v1/adjustments/{id}/review` | `MANAGER` | Aprova ou rejeita um ajuste (`decision: "APPROVED" \| "REJECTED"`) e recalcula o dia. |
| `DELETE` | `/api/v1/adjustments/{id}` | `MANAGER` | Exclui uma solicitação de ajuste informando `reason` na query. |
| `PUT` | `/api/v1/adjustments/admin/{id}/revert-status` | `MAINTAINER` | Reverte o status de um ajuste já avaliado e recalcula a apuração do dia. |

## 7. Apurações diárias, anomalias e espelhos (`/api/v1/daily-summaries`, `/api/v1/anomalies`, `/api/v1/timesheets`)

Controllers: [`daily_summary_router.py`](../app/features/daily_summaries/daily_summary_router.py) e [`timesheet_router.py`](../app/features/timesheets/timesheet_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `POST` | `/api/v1/daily-summaries/admin/reprocess` | `MAINTAINER` | Enfileira o reprocessamento das apurações diárias de um período (`start_date`, `end_date`) e lista opcional `user_ids`. |
| `GET` | `/api/v1/anomalies` | `MANAGER` | Lista anomalias do mês (batidas ímpares, faltas, atrasos ou horas excedentes) por `month`, `year` e `user_id` opcional. |
| `GET` | `/api/v1/timesheets/user/{user_id}/pdf` | `MANAGER` | Baixa o espelho de ponto em PDF de um funcionário no mês/ano. |
| `GET` | `/api/v1/timesheets/all/pdf` | `MANAGER` | Baixa um `.zip` com os espelhos de ponto em PDF da equipe (ou de `employee_ids`). |

## 8. Folha de ponto (`/api/v1/payroll`)

Controller: [`app/features/payroll/payroll_router.py`](../app/features/payroll/payroll_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/payroll/` | `MANAGER` | Lista os meses da folha no `year` informado (`OPEN` ou `CLOSED`). |
| `POST` | `/api/v1/payroll/{year}/{month}/transitions` | `MANAGER` | Fecha (`action: "close"`) ou reabre (`action: "reopen"`, exigindo `observation`) a folha do mês. |
| `GET` | `/api/v1/payroll/{closure_id}/download-report` | `MANAGER` | Baixa o relatório salvo no fechamento `closure_id`. |
| `POST` | `/api/v1/payroll/{closure_id}/legacy-report` | `MANAGER` | Anexa um relatório legado (`.xlsx` ou `.pdf`) a um fechamento. |

## 9. Relatórios e dashboards (`/api/v1/reports` e `/api/v1/dashboard`)

Controller: [`app/features/reports/report_router.py`](../app/features/reports/report_router.py). Detalhes em [`relatorios-e-excel.md`](relatorios-e-excel.md).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/reports/dashboard` | `EMPLOYEE` / `MANAGER` | Retorna os dados do dashboard conforme o perfil do usuário logado. |
| `GET` | `/api/v1/reports/my/dashboard` | `EMPLOYEE` | Retorna saldo do mês, horas trabalhadas e últimas batidas do funcionário. |
| `GET` | `/api/v1/dashboard/manager` | `MANAGER` | Retorna os indicadores da equipe no dia (presentes, pendências e alertas). |
| `GET` | `/api/v1/reports/history` | `EMPLOYEE` (próprio) / `MANAGER` | Retorna o histórico diário de batidas e saldos por `user_id`, `month` e `year`. |
| `GET` | `/api/v1/reports/team-hours` | `MANAGER` | Retorna o total de horas trabalhadas pela equipe e por funcionário no mês/ano. |
| `GET` | `/api/v1/reports/user/{user_id}` | `EMPLOYEE` (próprio) / `MANAGER` | Retorna o relatório detalhado de um funcionário no mês/ano. |
| `GET` | `/api/v1/reports/export/excel` | `MANAGER` | Baixa a planilha `.xlsx` do mês (`regenerate=true` disponível para `MAINTAINER`). |
| `GET` | `/api/v1/reports/operational-export` | `MANAGER` | Baixa o JSON operacional do mês (`kind=marcacoes` individual ou coletivo, e `kind=jornada`). |

## 10. Empresa, feriados e impressoras (`/api/v1/companies`, `/api/v1/holidays`, `/api/v1/printers`)

Controllers: [`company_router.py`](../app/features/companies/company_router.py), [`holiday_router.py`](../app/features/holidays/holiday_router.py) e [`printer_router.py`](../app/features/printers/printer_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/companies/` | `EMPLOYEE` | Retorna os dados da empresa e a URL da logo. |
| `POST` | `/api/v1/companies/` | `MAINTAINER` | Cria o cadastro da empresa (CNPJ, razão social, endereço e tolerância). |
| `PUT` | `/api/v1/companies/` | `MAINTAINER` | Atualiza os dados da empresa. |
| `POST` | `/api/v1/companies/logo` | `MAINTAINER` | Envia e valida a imagem de logo da empresa. |
| `GET` | `/api/v1/holidays/` | `EMPLOYEE` | Lista os feriados cadastrados. |
| `POST` | `/api/v1/holidays/` | `MANAGER` | Cadastra um feriado. |
| `DELETE` | `/api/v1/holidays/{id}` | `MANAGER` | Exclui um feriado pelo ID. |
| `GET` | `/api/v1/printers/` | `MANAGER` | Lista as impressoras térmicas ESC/POS (`skip`, `limit`). |
| `GET` | `/api/v1/printers/{printer_id}` | `MANAGER` | Busca uma impressora pelo ID. |
| `POST` | `/api/v1/printers/` | `MANAGER` | Cadastra uma impressora térmica na rede. |
| `PATCH` | `/api/v1/printers/{printer_id}` | `MANAGER` | Atualiza nome, IP, porta ou status da impressora. |
| `DELETE` | `/api/v1/printers/{printer_id}` | `MANAGER` | Remove uma impressora (`204 No Content`). |

## 11. Coletores biométricos e firmware OTA (`/api/v1/devices`, `/api/v1/device-credentials`, `/api/v1/biometrics`, `/api/v1/firmware`)

Controller: [`app/features/devices/device_router.py`](../app/features/devices/device_router.py).

| Método | Rota | Permissão / Chave | O que faz |
| --- | --- | --- | --- |
| `POST` | `/api/v1/devices/punch` | `X-Device-API-Key` | Registra a batida enviada pelo coletor biométrico e aciona a impressão do comprovante. |
| `GET` | `/api/v1/devices/time` | `X-Device-API-Key` | Retorna o horário do servidor para acertar o relógio do coletor. |
| `POST` | `/api/v1/devices/verify-manager` | `X-Device-API-Key` | Valida senha ou digital de gestor para abrir o menu administrativo no coletor. |
| `GET` | `/api/v1/device-credentials/` | `MAINTAINER` | Lista as credenciais cadastradas para os coletores. |
| `POST` | `/api/v1/device-credentials/` | `MAINTAINER` | Cria uma credencial de coletor (`device_id` e secret exibido no cadastro). |
| `PUT` | `/api/v1/device-credentials/{id}` | `MAINTAINER` | Edita a descrição, ativa/desativa ou troca o secret do coletor. |
| `DELETE` | `/api/v1/device-credentials/{id}` | `MAINTAINER` | Exclui a credencial de um coletor. |
| `GET` | `/api/v1/biometrics/available-sensor-indices` | `MANAGER` | Lista as posições livres na memória do sensor biométrico. |
| `GET` | `/api/v1/firmware/` | `MAINTAINER` | Lista as versões de firmware OTA salvas. |
| `POST` | `/api/v1/firmware/upload` | `MAINTAINER` | Faz upload de um arquivo `.bin` de firmware para uma `version`. |
| `PUT` | `/api/v1/firmware/{version}` | `MAINTAINER` | Substitui o binário de uma versão de firmware existente. |
| `GET` | `/api/v1/firmware/check` | `X-Device-API-Key` | Informa ao coletor qual é a versão mais recente de firmware disponível. |
| `GET` | `/api/v1/firmware/download` | `X-Device-API-Key` | Baixa o arquivo `firmware_{version}.bin` para atualização OTA no ESP32. |

## 12. Auditoria e logs de rotinas (`/api/v1/audit` e `/api/v1/routine-logs`)

Controller: [`app/features/system/system_router.py`](../app/features/system/system_router.py).

| Método | Rota | Permissão | O que faz |
| --- | --- | --- | --- |
| `GET` | `/api/v1/audit/` | `MANAGER` | Lista os logs de auditoria por `action`, `start_date`, `end_date`, `order_by`, `skip` e `limit`, incluindo o campo `schedule_change_summary` nos eventos de expediente. |
| `GET` | `/api/v1/routine-logs/` | `MAINTAINER` | Lista o histórico de execução das rotinas (`routine_type`, `status`, `start_date`, `end_date`). |
| `GET` | `/api/v1/routine-logs/jobs/{job_id}` | `MAINTAINER` | Retorna o status e detalhes de execução de um job da fila `background_jobs`. |
| `POST` | `/api/v1/routine-logs/jobs/{job_id}/retry` | `MAINTAINER` | Reagenda um job que falhou na fila `background_jobs`. |
