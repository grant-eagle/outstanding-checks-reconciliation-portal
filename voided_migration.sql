-- Run this in the Supabase SQL Editor to create the voided checks table.

CREATE TABLE IF NOT EXISTS voided_checks (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    payment_date DATE        NOT NULL,
    check_number TEXT        NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL,
    subsidiary   TEXT        NOT NULL,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voided_check_number ON voided_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_voided_subsidiary   ON voided_checks(subsidiary);

ALTER TABLE voided_checks ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT ON voided_checks TO anon;

CREATE POLICY "voided_select" ON voided_checks FOR SELECT TO anon USING (true);
CREATE POLICY "voided_insert" ON voided_checks FOR INSERT TO anon WITH CHECK (true);
