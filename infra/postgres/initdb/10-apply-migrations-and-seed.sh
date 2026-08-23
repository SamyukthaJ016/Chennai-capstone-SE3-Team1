#!/usr/bin/env bash
set -Eeuo pipefail

MIGRATIONS_DIR=${MIGRATIONS_DIR:-/migrations}
SEED_DIR=${SEED_DIR:-/seed}

psql_run() {
    psql \
        --no-psqlrc \
        --quiet \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB" \
        --set ON_ERROR_STOP=1 \
        "$@"
}

log() { printf '[init] %s\n' "$*"; }

shopt -s nullglob

migrations=("$MIGRATIONS_DIR"/*.sql)
if [ ${#migrations[@]} -eq 0 ]; then
    log "ERROR: no .sql files found in $MIGRATIONS_DIR"
    log "       is the repository mounted? see infra/postgres/docker-compose.yml"
    exit 1
fi

log "applying ${#migrations[@]} migration(s) from $MIGRATIONS_DIR"
for file in "${migrations[@]}"; do
    log "  apply $(basename "$file")"
    psql_run --file "$file"
    checksum=$(sha256sum "$file" | cut -d' ' -f1)
    psql_run --command "INSERT INTO schema_migrations (filename, checksum)
                        VALUES ('$(basename "$file")', '${checksum}')
                        ON CONFLICT (filename) DO UPDATE
                        SET checksum = EXCLUDED.checksum, applied_at = now();"
done

seeds=("$SEED_DIR"/*.csv)

if [ ${#seeds[@]} -eq 0 ]; then
    log "no .csv files in $SEED_DIR; skipping seed load"
else
    log "loading ${#seeds[@]} seed file(s) from $SEED_DIR"
    for file in "${seeds[@]}"; do
        base=$(basename "$file" .csv)
        table=${base#*_}
        if [ "$table" = "$base" ]; then
            log "ERROR: $(basename "$file") must be named <number>_<table>.csv"
            exit 1
        fi

        header=$(head -n 1 "$file" | tr -d '\r')
        if [ -z "$header" ]; then
            log "ERROR: $(basename "$file") has no header row"
            exit 1
        fi

        log "  load $(basename "$file") -> ${table}"
        psql_run --command "\copy \"${table}\" (${header}) FROM '${file}' WITH (FORMAT csv, HEADER true)"
    done
fi

log "resyncing sequences past the seeded ids"
psql_run --command "SELECT count(*) AS sequences_resynced FROM fn_resync_sequences();"

log "database is built and ready"
