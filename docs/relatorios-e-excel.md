# Relatórios, planilhas Excel, PDFs e hash de autenticidade

[![OpenPyXL](https://img.shields.io/badge/OpenPyXL-3.1%2B-217346)](https://openpyxl.readthedocs.io/) [![ReportLab](https://img.shields.io/badge/ReportLab-5.0%2B-B30B00)](https://www.reportlab.com/) [![Pillow](https://img.shields.io/badge/Pillow-12.3%2B-3776AB)](https://python-pillow.org/) [![QRCode](https://img.shields.io/badge/qrcode-8.2%2B-000000)](https://pypi.org/project/qrcode/) [![Hashids](https://img.shields.io/badge/hashids-1.3%2B-5A4FCF)](https://pypi.org/project/hashids/)

Funcionamento da geração da planilha mensal em Excel, dos espelhos de ponto em PDF/ZIP, dos comprovantes de batida, da exportação operacional em JSON e do cálculo do hash de autenticidade. A lista de endpoints está em [`endpoints.md`](endpoints.md).

## Bibliotecas utilizadas

- `openpyxl`: montagem da planilha `.xlsx` mensal com aba de resumo, abas por funcionário e metadados do arquivo.
- `reportlab`: geração dos espelhos de ponto mensais em PDF e dos comprovantes individuais de batida.
- `qrcode` e `pillow`: geração dos QR Codes nos PDFs e validação/redimensionamento da logo da empresa.
- `hashids`: geração do código curto `short_id` usado nas rotas de comprovante (`/api/v1/time-records/receipt/{short_id}`).

## Planilha mensal em Excel (`GET /api/v1/reports/export/excel`)

O [`ExcelService`](../app/features/reports/excel_service.py) gera o arquivo `.xlsx` do mês solicitado:

- Recebe `month`, `year`, filtro opcional `employee_ids` e a flag `regenerate`.
- Quando a folha do mês já foi fechada em `payroll_closures` e a consulta é da equipe completa, a rota devolve o arquivo `.xlsx` salvo no fechamento. Usuários com perfil `MAINTAINER` podem passar `regenerate=true` para gerar uma nova planilha com os dados atuais do banco sem sobrescrever o arquivo salvo no fechamento.
- A planilha contém uma aba de resumo da equipe e uma aba para cada funcionário com as batidas do dia, jornada prevista (a partir do `daily_minutes` do expediente vigente), saldo diário, feriados, abonos e totais do mês.
- Para meses anteriores ao uso do sistema, `POST /api/v1/payroll/{closure_id}/legacy-report` permite enviar um arquivo `.xlsx` ou `.pdf` legado (validado por magic bytes e limitado por `UPLOAD_LEGACY_REPORT_MAX_BYTES`), que fica disponível para download em `GET /api/v1/payroll/{closure_id}/download-report`.

## Espelhos de ponto em PDF e lote ZIP

O [`TimesheetService`](../app/features/timesheets/timesheet_service.py) gera os espelhos de ponto para assinatura:

- Por funcionário (`GET /api/v1/timesheets/user/{user_id}/pdf`): gera o PDF do mês/ano com dados da empresa, batidas diárias, horas trabalhadas, horas extras, atrasos, ajustes aprovados e campo de assinatura.
- Em lote (`GET /api/v1/timesheets/all/pdf`): gera um `.zip` com os PDFs de todos os funcionários ativos (ou da lista `employee_ids`).
- Se ocorrer falha ao gerar o PDF de algum funcionário durante a criação do lote, os demais PDFs são mantidos no `.zip` junto com o arquivo `manifesto_exportacao.json` listando os gerados e as falhas, e a resposta inclui os headers `X-Export-Status` (`complete` ou `partial`), `X-Export-Generated-Count` e `X-Export-Failed-Count`. Se nenhum PDF puder ser gerado, a rota retorna `503 Service Unavailable`.

## Exportação operacional (`GET /api/v1/reports/operational-export`)

O [`OperationalExportService`](../app/features/reports/operational_export_service.py) exporta os dados do período (`month`, `year`) em JSON para conferência de gestores e mantenedores em dois formatos (`kind`):

1. `kind=marcacoes`:
   - Informando `user_id`: exporta todas as batidas do funcionário no mês, incluindo data/hora, tipo (`ENTRY`/`EXIT`), dispositivo, se foi desconsiderada (`ignorada`), data de exclusão e vínculo com ajustes.
   - Sem `user_id` (coletivo): exporta em uma única consulta as batidas do mês de todos os funcionários, incluindo o bloco `usuario` (`id` e `nome`) em cada registro.
2. `kind=jornada`:
   - Exige `user_id` e exporta o relatório detalhado da jornada diária e os totalizadores do funcionário no mês.

## Hash determinístico de autenticidade (`sha256`)

Todos os arquivos exportados recebem um hash calculado por [`document_authenticity.py`](../app/shared/document_authenticity.py) diretamente sobre os dados vindos do banco:

1. Os dados de domínio do documento (tipo, período, empresa, funcionário, batidas e totais) são normalizados e serializados em JSON canônico (`sort_keys=True`, sem espaços e com datas em ISO-8601), ignorando campos de horário de geração.
2. A função calcula o `SHA-256` desse conteúdo, gerando o identificador `sha256:<hex_digest>`.
3. O hash é gravado nos metadados do arquivo e no header HTTP `X-Document-Hash`:
   - Planilhas Excel (`.xlsx`): propriedades `subject` e `keywords` do arquivo e header `X-Document-Hash`.
   - Espelhos de ponto e comprovantes (`.pdf`): campos `Subject` e `Keywords` do PDF e header `X-Document-Hash`.
   - Exportações operacionais (`.json`): campo `"metadados": {"hash_autenticidade": "sha256:<hex_digest>"}` no JSON e header `X-Document-Hash`.
