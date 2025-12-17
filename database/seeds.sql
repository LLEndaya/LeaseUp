-- database/seeds.sql
-- Sample data INSERTs for LeaseUp (renamed from sample_data.sql)

INSERT INTO property (id, name, address) VALUES
(1, 'Greenfield Heights', '123 Main St'),
(2, 'Sunrise Residences', '456 Oak Ave'),
(3, 'Urban Plaza Apts', '789 Pine Blvd'),
(4, 'Riverside Towers', '321 Elm Way');

INSERT INTO unit (id, number, status, property_id) VALUES
(1, 'Room 1', 'occupied', 1),
(2, 'Room 2', 'vacant', 2),
(3, 'Room 3', 'vacant', 3),
(4, 'Room 4', 'occupied', 4);

INSERT INTO tenant (id, name, phone, email) VALUES
(1, 'Juan Dela Cruz', '09171234567', 'juan@example.com'),
(2, 'Maria Santos', '09187654321', 'maria@example.com');

INSERT INTO lease (id, unit_id, tenant_id, lease_request_id, start_date, end_date, monthly_rent) VALUES
(1, 1, 1, NULL, DATE('now'), DATE('now', '+365 days'), 5000.0),
(2, 4, 2, NULL, DATE('now'), DATE('now', '+365 days'), 6500.0);

INSERT INTO emergency_contact (id, unit_id, unit_identifier, name, phone) VALUES
(1, 1, 'Room 1', 'Juan Dela Cruz', '09171234567'),
(2, 4, 'Room 4', 'Maria Santos', '09187654321');

INSERT INTO maintenance_request (id, unit_id, description, status, created_at) VALUES
(1, 4, 'Leaky faucet reported in Room 4. Needs plumbing attention.', 'open', DATETIME('now'));

INSERT INTO "user" (id, username, password_hash) VALUES
(1, 'admin', '');

INSERT INTO tenant_user (id, username, email, password_hash, phone, created_at) VALUES
(1, 'tenant', 'tenant@example.com', '', NULL, DATETIME('now'));

INSERT INTO lease_request (id, unit_id, tenant_user_id, tenant_id, start_date, end_date, monthly_rent, notes, status, created_at) VALUES
(1, 2, 1, NULL, DATE('now', '+7 days'), DATE('now', '+1 year'), 4500.0, 'Testing booking', 'pending', DATETIME('now'));

