# Operação da API

## Proteção contra rajadas de requisições

Por padrão, cada endereço IP pode fazer até 30 requisições em uma janela móvel de um segundo e 600 em uma janela móvel de 60 segundos. Login, renovação de sessão e alteração de senha compartilham ainda um limite adicional de 60 requisições por minuto. Requisições acima do limite recebem HTTP `429`, mensagem explicativa e o cabeçalho `Retry-After` com o tempo de espera. A aplicação não mantém conexões abertas durante essa espera e não repete operações automaticamente.

Como funcionários na mesma rede podem compartilhar um IP público, ajuste os valores à quantidade de usuários e ao padrão real de tráfego. Os limites e a ativação estão em [README.env.md](README.env.md). Os contadores ficam na memória da instância e são reiniciados quando a aplicação reinicia. Requisições diretas de `127.0.0.1` e `::1` sem cabeçalhos de proxy são isentas.

O IP vem da conexão direta. Se houver um proxy reverso, configure `TRUSTED_PROXY_CIDRS` apenas com as redes dos proxies sob seu controle e garanta que eles substituam os cabeçalhos de origem fornecidos pelo cliente. Um proxy local confiável não recebe isenção de localhost: suas requisições são limitadas pelo IP encaminhado. Sem essa configuração, todos os clientes atrás do proxy podem compartilhar uma única cota; confiar em proxies não controlados permite falsificar a origem. Proxies locais devem encaminhar o IP de origem: se omitirem todos os cabeçalhos de origem e não forem configurados como confiáveis, o tráfego pode ser confundido com acesso local direto.

A limitação na aplicação reduz abuso por origem, mas não impede a saturação da rede por ataques distribuídos. Para esse cenário, use a proteção contra DDoS disponibilizada pelo provedor de rede ou infraestrutura e mantenha monitoramento de tráfego e disponibilidade.

## Verificação e rotinas

`GET /api/v1/health` informa o estado básico da aplicação. `GET /api/v1/ready` verifica a conexão com PostgreSQL e a revisão do schema. Use a prontidão para avaliar se a instância pode receber tráfego. Mantenha a migração do banco atualizada com `uv run alembic upgrade head`.

A fila de tarefas é persistida no PostgreSQL; rotinas agendadas executam notificações, manutenção e backups conforme o ambiente. Configure SMTP, Telegram, retenção e horários em [README.env.md](README.env.md). O NTP é usado para sincronizar o horário. Os arquivos de upload e backups devem ficar em armazenamento persistente, com cópia e restauração verificadas.

## Auditoria de expedientes

As operações em lote registram um resumo legível e o estado dos expedientes envolvidos. Atualizações guardam os estados anterior e posterior; exclusões guardam o estado anterior. O nome é registrado quando disponível, com o identificador como referência.

O campo `schedule_snapshot_zlib` começa por `v1:`. O restante é uma string Base64 de um documento JSON UTF-8 comprimido com zlib. O objeto contém `valid_from`, `valid_until` e `schedules`, com identificador, funcionário, dia, duração em minutos, horários e configuração de excedente de cada expediente. Para recuperar os dados em Python:

```python
import base64
import json
import zlib

snapshot = json.loads(zlib.decompress(base64.b64decode(valor.removeprefix("v1:"))))
```

A compressão reduz a repetição dos campos e permite recuperar o conteúdo; ela não é assinatura digital nem comprova integridade contra alteração. Registros anteriores permanecem intactos e são apresentados usando apenas os dados efetivamente registrados.
