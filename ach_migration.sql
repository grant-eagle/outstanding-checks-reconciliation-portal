-- Run this in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS issued_ach (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    payment_date DATE        NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL,
    subsidiary   TEXT        NOT NULL,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cleared_ach (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    date         DATE        NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL,
    subsidiary   TEXT        NOT NULL,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issued_ach_date       ON issued_ach(payment_date);
CREATE INDEX IF NOT EXISTS idx_issued_ach_subsidiary ON issued_ach(subsidiary);
CREATE INDEX IF NOT EXISTS idx_cleared_ach_date      ON cleared_ach(date);
CREATE INDEX IF NOT EXISTS idx_cleared_ach_subsidiary ON cleared_ach(subsidiary);

ALTER TABLE issued_ach  ENABLE ROW LEVEL SECURITY;
ALTER TABLE cleared_ach ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT ON issued_ach  TO anon;
GRANT SELECT, INSERT ON cleared_ach TO anon;

CREATE POLICY "issued_ach_select"  ON issued_ach  FOR SELECT TO anon USING (true);
CREATE POLICY "issued_ach_insert"  ON issued_ach  FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "cleared_ach_select" ON cleared_ach FOR SELECT TO anon USING (true);
CREATE POLICY "cleared_ach_insert" ON cleared_ach FOR INSERT TO anon WITH CHECK (true);
