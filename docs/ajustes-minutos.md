# Duração dos ajustes

O banco armazena a duração solicitada e aprovada em minutos inteiros nas colunas `amount_minutes` e `approved_amount_minutes`. Para criar abonos ou revisar excedentes, envie `amount_minutes` ou `approved_amount_minutes` como números inteiros. As respostas de ajustes incluem esses campos; relatórios também podem apresentá-los.

Para manter integrações anteriores, a API ainda aceita e retorna `amount_hours` e `approved_amount_hours`. Não envie a mesma duração nas duas unidades na mesma requisição. Conversões de horas para minutos arredondam para o inteiro mais próximo; nos empates, afastam-se de zero. Valores positivos que arredondariam para zero não são aceitos para abonos.

A migração 014 aplica o mesmo arredondamento aos registros existentes. Ao desfazê-la, os valores em horas são reconstruídos a partir dos minutos e não recuperam frações de minuto descartadas na migração.
