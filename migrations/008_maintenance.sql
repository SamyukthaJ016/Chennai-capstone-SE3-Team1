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

        PERFORM setval(seq, GREATEST(mx, 1), mx > 0);

        sequence_name := seq;
        set_to        := GREATEST(mx, 1);
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

COMMIT;
