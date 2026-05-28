-- Run this in the Supabase SQL Editor to create the seed checks table.

CREATE TABLE IF NOT EXISTS seed_checks (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    check_number TEXT        NOT NULL,
    payment_date DATE        NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL,
    subsidiary   TEXT        NOT NULL,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seed_check_number ON seed_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_seed_subsidiary   ON seed_checks(subsidiary);

ALTER TABLE seed_checks ENABLE ROW LEVEL SECURITY;

-- anon key: read and insert only. No UPDATE or DELETE = records are protected.
GRANT SELECT, INSERT ON seed_checks TO anon;

CREATE POLICY "seed_select" ON seed_checks FOR SELECT TO anon USING (true);
CREATE POLICY "seed_insert" ON seed_checks FOR INSERT TO anon WITH CHECK (true);
