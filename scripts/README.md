# Ferramentas PostgreSQL

Execute os comandos na raiz do projeto com o ambiente configurado. Os scripts de backup operam sobre o PostgreSQL definido em `SQLALCHEMY_DATABASE_URI`.

| Comando | Finalidade |
| --- | --- |
| `make dump` | Cria um backup completo criptografado. |
| `make db-dump-ddl` | Exporta a estrutura do banco. |
| `make db-dump-data` | Exporta os dados com manifesto. |
| `make db-restore-test` | Valida a restauração em um banco temporário. |
| `make restore` | Restaura o backup localizado automaticamente. |
| `uv run python -m scripts.backfill_daily_summaries` | Prévia do recálculo de resumos; acrescente `--execute` para aplicar. |

A restauração substitui os dados do banco de destino. Antes de executá-la, confira o destino, preserve o backup e teste a recuperação em ambiente separado. O backup do banco não inclui os arquivos de `UPLOAD_DIR`, que devem ser preservados junto com ele. A chave `SECRET_KEY` usada para criptografar o backup é necessária para restaurá-lo.

Para validar um arquivo sem gravar dados:

```bash
uv run python scripts/apply_sql_to_postgresql.py --file caminho/backup.zip.enc --restore --dry-run
```
