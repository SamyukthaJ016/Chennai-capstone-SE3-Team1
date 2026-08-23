-- =====================================================================
-- 009_maintenance.sql
-- Team 1 - Trade Database (Postgres) | SEC3-95
--
-- fn_resync_sequences() moves every SERIAL sequence past the largest id
-- currently in its table.
--
-- Why this is needed: the seed CSVs carry EXPLICIT ids (so that
-- orders.client_id can point at a known client). COPY does not advance
-- the sequence when an id is supplied, so without this the application's
-- first INSERT would try to reuse id 1 and collide with seed data.
--
-- It lives here, as a function in the schema, rather than being pasted
-- into both scripts/apply_db.py and infra/postgres/initdb/. Two copies
-- of the same logic drift; one definition cannot.
--
-- Safe to call at any time: it never lowers a sequence below its current
-- value's table maximum, and it is a no-op on empty tables.
-- =====================================================================
BEGIN;

CREATE OR REPLACE FUNCTION fn_resync_sequences()
RETURNS TABLE (sequence_name TEXT, set_to BIGINT) AS $$
DECLARE
    r   RECORD;
    seq TEXT;
    mx  BIGINT;
BEGIN
    FOR r IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables  t
          ON t.table_schema = c.table_schema
         AND t.table_name   = c.table_name
        WHERE c.table_schema = 'public'
          AND t.table_type   = 'BASE TABLE'
          AND (c.column_default LIKE 'nextval(%' OR c.is_identity = 'YES')
        ORDER BY c.table_name, c.column_name
    LOOP
        seq := pg_get_serial_sequence(quote_ident(r.table_name), r.column_name);
        CONTINUE WHEN seq IS NULL;

        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name)
           INTO mx;

        -- is_called = false on an empty table, so the next value is 1.
        PERFORM setval(seq, GREATEST(mx, 1), mx > 0);

        sequence_name := seq;
        set_to        := GREATEST(mx, 1);
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_resync_sequences() IS
    'Move every SERIAL sequence past the largest id in its table. Call after loading seed data that carries explicit ids.';

COMMIT;
