-- Run this in the Supabase SQL Editor to create the two tables.

CREATE TABLE IF NOT EXISTS issued_checks (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    payment_date DATE        NOT NULL,
    check_number TEXT        NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cleared_checks (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    date         DATE        NOT NULL,
    description  TEXT,
    check_number TEXT        NOT NULL,
    status       TEXT,
    amount       NUMERIC(14, 2) NOT NULL,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issued_check_number  ON issued_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_cleared_check_number ON cleared_checks(check_number);
