#!/bin/bash
# Apply schema/*.sql in dependency order against CCE_METADATA_DATABASE_URL
# (or POSTGRES_* vars matching docker-compose.yaml's defaults). Idempotent:
# every statement is CREATE ... IF NOT EXISTS.
set -euo pipefail

SCHEMA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${CCE_METADATA_DATABASE_URL:-}" ]; then
    DSN="$CCE_METADATA_DATABASE_URL"
else
    DSN="postgresql://${POSTGRES_USER:-cce_admin}:${POSTGRES_PASSWORD:-cce_password}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-cce_metadata}"
fi

for f in "$SCHEMA_DIR"/01_core_hierarchy.sql \
         "$SCHEMA_DIR"/02_snapshots.sql \
         "$SCHEMA_DIR"/03_metadata.sql \
         "$SCHEMA_DIR"/04_relationships.sql; do
    echo "Applying $f ..."
    psql "$DSN" -v ON_ERROR_STOP=1 -f "$f"
done

echo "Schema applied."
