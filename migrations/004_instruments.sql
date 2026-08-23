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

COMMIT;
