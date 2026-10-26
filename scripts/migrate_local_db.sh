#!/usr/bin/env bash
# Aplica, em ordem, as migrações de database/migrations/ ao banco LOCAL do Compose.
# Todas são idempotentes. Faça backup antes: ./scripts/backup_local_db.sh
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
echo "Atenção: aplicando migrações somente ao serviço PostgreSQL local 'database'."
for file in "$root"/database/migrations/*.sql; do
  echo "-> $(basename "$file")"
  docker compose exec -T database sh -ec \
    'exec psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
    < "$file"
done
echo "Migrações aplicadas."
