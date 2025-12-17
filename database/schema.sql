-- database/schema.sql
-- Schema definitions for LeaseUp
PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- Users (admin)
CREATE TABLE "user" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

-- TenantUser (accounts for tenants who sign up)
CREATE TABLE tenant_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    phone TEXT,
    created_at DATETIME
);

CREATE TABLE property (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT
);

CREATE TABLE unit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL,
    status TEXT DEFAULT 'vacant',
    property_id INTEGER,
    FOREIGN KEY(property_id) REFERENCES property(id)
);

CREATE TABLE tenant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT
);

CREATE TABLE lease (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER,
    tenant_id INTEGER,
    lease_request_id INTEGER,
    start_date DATE,
    end_date DATE,
    monthly_rent REAL,
    FOREIGN KEY(unit_id) REFERENCES unit(id),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(lease_request_id) REFERENCES lease_request(id)
);
-- One-to-one link: lease_request -> lease (lease_request_id on lease)
CREATE UNIQUE INDEX IF NOT EXISTS idx_lease_lease_request_id ON lease (lease_request_id);

CREATE TABLE payment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lease_id INTEGER,
    amount REAL NOT NULL,
    date DATETIME,
    FOREIGN KEY(lease_id) REFERENCES lease(id)
);

CREATE TABLE maintenance_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER,
    description TEXT,
    status TEXT DEFAULT 'open',
    created_at DATETIME
);

CREATE TABLE lease_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER,
    tenant_user_id INTEGER,
    tenant_id INTEGER,
    start_date DATE,
    end_date DATE,
    monthly_rent REAL,
    notes TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATETIME,
    FOREIGN KEY(unit_id) REFERENCES unit(id),
    FOREIGN KEY(tenant_user_id) REFERENCES tenant_user(id),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);
-- Optional monthly_rent in request; when approved a Lease is created (may reference this request).

CREATE TABLE emergency_contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER,
    unit_identifier TEXT,
    name TEXT,
    phone TEXT,
    FOREIGN KEY(unit_id) REFERENCES unit(id)
);

COMMIT;
PRAGMA foreign_keys = ON;
