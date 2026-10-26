#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
mkdir -p backups
file="backups/salutem-local-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T database sh -ec \
  'exec pg_dump --format=custom --no-owner --no-acl --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
  > "$file"
chmod 600 "$file"
printf 'Backup do banco local salvo em %s\n' "$file"
printf 'Proteja e copie esse arquivo para o local de backup definido pela Salutem.\n'
