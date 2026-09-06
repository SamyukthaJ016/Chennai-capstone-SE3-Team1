BEGIN;

CREATE TABLE instruments (
    instrument_id   VARCHAR(20)     PRIMARY KEY,
    instrument_name VARCHAR(150)    NOT NULL UNIQUE,
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    updated_on      TIMESTAMP,
    CONSTRAINT chk_instruments_id_not_blank CHECK (length(btrim(instrument_id)) > 0)
);

CREATE INDEX idx_instruments_active ON instruments(active);

CREATE OR REPLACE FUNCTION fn_instruments_no_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'instrument % cannot be deleted; set active = FALSE instead', OLD.instrument_id
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_instruments_no_delete
    BEFORE DELETE ON instruments
    FOR EACH ROW EXECUTE FUNCTION fn_instruments_no_delete();

COMMIT;
