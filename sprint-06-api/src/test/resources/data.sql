-- Seed data for unit and integration tests.
-- Matches the seed CSV files under /seed/ and the test fixtures in the mapper tests.

-- Clients (matches seed/020_clients.csv)
INSERT INTO clients (client_id, account_number, name, email, phone, account_state, wallet_balance, version, updated_on)
VALUES (1, 'IN45HDFC0000001234567', 'Aarav Mehta', 'aarav.mehta@example.com', '+919812345001', 'ACTIVE', 125000.00, 0, CURRENT_TIMESTAMP);
INSERT INTO clients (client_id, account_number, name, email, phone, account_state, wallet_balance, version, updated_on)
VALUES (2, 'IN45ICIC0000002345678', 'Diya Sharma', 'diya.sharma@example.com', '+919812345002', 'ACTIVE', 48250.50, 0, CURRENT_TIMESTAMP);
INSERT INTO clients (client_id, account_number, name, email, phone, account_state, wallet_balance, version, updated_on)
VALUES (3, 'IN45SBIN0000003456789', 'Rohan Iyer', 'rohan.iyer@example.com', '+919812345003', 'ACTIVE', 310400.75, 0, CURRENT_TIMESTAMP);
INSERT INTO clients (client_id, account_number, name, email, phone, account_state, wallet_balance, version, updated_on)
VALUES (4, 'IN45AXIS0000004567890', 'Meera Nair', 'meera.nair@example.com', '+919812345004', 'SUSPENDED', 15000.00, 0, CURRENT_TIMESTAMP);
INSERT INTO clients (client_id, account_number, name, email, phone, account_state, wallet_balance, version, updated_on)
VALUES (5, 'IN45KKBK0000005678901', 'Vikram Rao', 'vikram.rao@example.com', '+919812345005', 'ACTIVE', 92750.25, 0, CURRENT_TIMESTAMP);
INSERT INTO clients (client_id, account_number, name, email, phone, account_state, wallet_balance, version, updated_on)
VALUES (6, 'IN45YESB0000006789012', 'Sanya Kapoor', 'sanya.kapoor@example.com', '+919812345006', 'CLOSED', 0.00, 0, CURRENT_TIMESTAMP);

-- Instruments (matches seed/040_instruments.csv)
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('RELIANCE', 'Reliance Industries', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('TCS', 'Tata Consultancy Services', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('INFY', 'Infosys', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('HDFCBANK', 'HDFC Bank', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('ICICIBANK', 'ICICI Bank', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('ITC', 'ITC', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('TATAMOTORS', 'Tata Motors', TRUE, NULL);
INSERT INTO instruments (instrument_id, instrument_name, active, updated_on)
VALUES ('LEGACYCORP', 'Legacy Corp', FALSE, TIMESTAMP '2025-11-14 15:30:00');
