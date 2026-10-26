#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

echo "Atenção: este script aplica o schema SOMENTE ao serviço PostgreSQL local 'database' do Compose."
echo "Ele cria duas tabelas de negócio (setores, requisicoes) e a sequence local; não use o dump ERP."
docker compose exec -T database sh -ec \
  'exec psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
  < "$root/database/schema.sql"
