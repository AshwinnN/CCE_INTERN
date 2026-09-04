#!/bin/bash
# Apply cce_control migrations in dependency order against CCE_CONTROL_DATABASE_URL
# (or POSTGRES_* vars matching docker-compose.yaml's defaults). Idempotent:
# every statement is CREATE ... IF NOT EXISTS.
set -euo pipefail

SCHEMA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${CCE_CONTROL_DATABASE_URL:-}" ]; then
    DSN="$CCE_CONTROL_DATABASE_URL"
elif [ -n "${CCE_METADATA_DATABASE_URL:-}" ]; then
    DSN="$CCE_METADATA_DATABASE_URL"
else
    DSN="postgresql://${POSTGRES_USER:-cce_admin}:${POSTGRES_PASSWORD:-cce_password}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5434}/${POSTGRES_DB:-cce_control}"
fi

for f in "$SCHEMA_DIR"/001_registry.sql \
         "$SCHEMA_DIR"/002_metadata.sql \
         "$SCHEMA_DIR"/002_metadata_01_details.sql \
         "$SCHEMA_DIR"/002_metadata_02_relationships.sql \
         "$SCHEMA_DIR"/003_governance.sql \
         "$SCHEMA_DIR"/004_context.sql \
         "$SCHEMA_DIR"/005_runtime.sql \
         "$SCHEMA_DIR"/006_audit.sql; do
    echo "Applying $f ..."
    psql "$DSN" -v ON_ERROR_STOP=1 -f "$f"
done

echo "Schema applied."
