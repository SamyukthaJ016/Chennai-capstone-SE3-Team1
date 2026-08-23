#!/usr/bin/env bash
# =====================================================================
# infra/postgres/initdb/10-apply-migrations-and-seed.sh
# Team 1 - Trade Database (Postgres) | SEC3-95
#
# Runs once, automatically, the first time the container starts on an
# empty data volume. It does exactly what scripts/apply_db.py does:
#
#   1. apply every /migrations/*.sql in FILENAME ORDER
#   2. load  every /seed/*.csv       in FILENAME ORDER
#   3. resync the SERIAL sequences past the seeded ids
#
# psql runs with ON_ERROR_STOP=1 throughout and this script runs with
# `set -e`, so a migration or a row that cannot be mapped ABORTS the
# whole init. A half-built database is never left running and reported
# as healthy.
# =====================================================================
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

# ---------------------------------------------------------------------
# 1. migrations, in filename order
# ---------------------------------------------------------------------
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
    # Record it, so the ledger matches what scripts/apply_db.py would write
    # and a later run of that script does not try to re-apply anything.
    checksum=$(sha256sum "$file" | cut -d' ' -f1)
    psql_run --command "INSERT INTO schema_migrations (filename, checksum)
                        VALUES ('$(basename "$file")', '${checksum}')
                        ON CONFLICT (filename) DO UPDATE
                        SET checksum = EXCLUDED.checksum, applied_at = now();"
done

# ---------------------------------------------------------------------
# 2. seed data, in filename order
# ---------------------------------------------------------------------
seeds=("$SEED_DIR"/*.csv)

if [ ${#seeds[@]} -eq 0 ]; then
    log "no .csv files in $SEED_DIR; skipping seed load"
else
    log "loading ${#seeds[@]} seed file(s) from $SEED_DIR"
    for file in "${seeds[@]}"; do
        base=$(basename "$file" .csv)
        # 050_orders.csv -> orders. The number is load order only.
        table=${base#*_}
        if [ "$table" = "$base" ]; then
            log "ERROR: $(basename "$file") must be named <number>_<table>.csv"
            exit 1
        fi

        # Column list comes from the CSV header, so a file only has to
        # supply the columns it actually has; the rest take their DEFAULT.
        header=$(head -n 1 "$file" | tr -d '\r')
        if [ -z "$header" ]; then
            log "ERROR: $(basename "$file") has no header row"
            exit 1
        fi

        log "  load $(basename "$file") -> ${table}"
        # A row that cannot be mapped raises here and, with ON_ERROR_STOP
        # and set -e, takes the whole init down with it. It is never skipped.
        psql_run --command "\copy \"${table}\" (${header}) FROM '${file}' WITH (FORMAT csv, HEADER true)"
    done
fi

# ---------------------------------------------------------------------
# 3. sequences (defined in migrations/009_maintenance.sql)
# ---------------------------------------------------------------------
log "resyncing sequences past the seeded ids"
psql_run --command "SELECT count(*) AS sequences_resynced FROM fn_resync_sequences();"

log "database is built and ready"
