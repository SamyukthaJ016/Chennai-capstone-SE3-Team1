-- =====================================================================
-- 004_instruments.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- An instrument that stops trading is deactivated, never deleted, so
-- historical orders and holdings can still resolve their FK
-- (SEC3-94: "Model an instrument that has stopped trading without
--  removing the row, so that old orders still resolve").
--
-- delisted_on records WHEN it stopped trading, and the CHECK keeps the
-- two columns from disagreeing with each other.
-- =====================================================================
BEGIN;

CREATE TABLE instruments (
    instrument_id   SERIAL          PRIMARY KEY,
    instrument_name VARCHAR(150)    NOT NULL UNIQUE,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    delisted_on     TIMESTAMP,
    CONSTRAINT chk_instruments_delisted_consistent
        CHECK ( (is_active = TRUE  AND delisted_on IS NULL)
             OR (is_active = FALSE AND delisted_on IS NOT NULL) )
);

CREATE INDEX idx_instruments_is_active ON instruments(is_active);

-- An instrument row is never removed: old orders and holdings point at it.
CREATE OR REPLACE FUNCTION fn_instruments_no_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'instrument % cannot be deleted; set is_active = FALSE instead', OLD.instrument_id
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_instruments_no_delete
    BEFORE DELETE ON instruments
    FOR EACH ROW EXECUTE FUNCTION fn_instruments_no_delete();

COMMENT ON TABLE  instruments             IS 'Tradable instrument. Rows are never deleted; delisting sets is_active = FALSE.';
COMMENT ON COLUMN instruments.is_active   IS 'FALSE once the instrument stops trading. The row stays so historical orders still resolve.';
COMMENT ON COLUMN instruments.delisted_on IS 'When the instrument stopped trading. NULL exactly when is_active is TRUE.';

COMMIT;
