-- Run this in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS subsidiary_accounts (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    subsidiary       TEXT        NOT NULL,
    account_number   TEXT        NOT NULL,
    UNIQUE(subsidiary, account_number)
);

ALTER TABLE subsidiary_accounts ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT ON subsidiary_accounts TO anon;

CREATE POLICY "accounts_select" ON subsidiary_accounts FOR SELECT TO anon USING (true);
CREATE POLICY "accounts_insert" ON subsidiary_accounts FOR INSERT TO anon WITH CHECK (true);

-- Seed known account numbers
INSERT INTO subsidiary_accounts (subsidiary, account_number) VALUES
    ('CIC - FF',    '26830036'),
    ('CAdmin - LF', '26833523'),
    ('CHR - SF',    '26838851')
ON CONFLICT DO NOTHING;
