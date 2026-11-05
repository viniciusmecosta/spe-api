# Prévia textual de jornada

O mantenedor pode gerar uma prévia mensal por funcionário em `GET /api/v1/reports/aej-preview?user_id=<id>&month=<mês>&year=<ano>`. A resposta é um arquivo ISO-8859-1 com linhas delimitadas por `|` e terminadas em CRLF, inspirado nos registros 01, 03, 04, 05 e 99 do [leiaute AEJ do Ministério do Trabalho](https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/fiscalizacao-do-trabalho/leiaute-do-arquivo-eletronico-de-jornada-aej.pdf).

**É um rascunho incompleto, não fiscal e sem assinatura ICP-Brasil. Não é um AEJ oficial.** O nome do arquivo e o cabeçalho HTTP `X-Export-Status` indicam essa condição. O cabeçalho usa a versão `002` do leiaute; os segundos são ajustados para `00`, e a exportação operacional JSON preserva o instante completo. A duração contratual reproduz os minutos cadastrados, sem verificar nem aplicar redução de hora noturna. Para horários noturnos é necessária revisão manual; o cabeçalho HTTP `X-Export-Limitations` também registra essa limitação.

CPF e horários ausentes permanecem vazios; horários sobrepostos não são escolhidos arbitrariamente. Motivos não cadastrados permanecem vazios. O arquivo não contém identificação de REP, identificação do desenvolvedor do PTRP, ausências ou movimentos de banco de horas. As marcações do ESP32 e demais fontes são identificadas como outras fontes; inclusões administrativas identificáveis usam a categoria manual. Não há identificação fictícia de REP nem declaração de assinatura. Os valores devem ser revisados antes de qualquer uso.

O AFD deve ser produzido pelo REP com os requisitos próprios de armazenamento e integridade. O ESP32 usado neste projeto é um coletor e não disponibiliza esse arquivo; a API não apresenta suas exportações como AFD oficial.
