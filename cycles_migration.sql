-- Run this in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS subsidiary_cycles (
    id               UUID  DEFAULT gen_random_uuid() PRIMARY KEY,
    subsidiary       TEXT  NOT NULL,
    cycle_identifier TEXT  NOT NULL,
    UNIQUE(subsidiary, cycle_identifier)
);

ALTER TABLE subsidiary_cycles ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT ON subsidiary_cycles TO anon;

CREATE POLICY "cycles_select" ON subsidiary_cycles FOR SELECT TO anon USING (true);
CREATE POLICY "cycles_insert" ON subsidiary_cycles FOR INSERT TO anon WITH CHECK (true);

-- Seed the known cycle mappings
INSERT INTO subsidiary_cycles (subsidiary, cycle_identifier) VALUES
    ('CIC - FF',    'Fully Insured Subscriber Payment Cycle'),
    ('CIC - FF',    'Fully Insured Supplier Payment Cycle'),
    ('CAdmin - LF', 'Level Funded EPOValue Supplier Payment Cycle'),
    ('CAdmin - LF', 'Level Funded Subscriber Payment Cycle'),
    ('CAdmin - LF', 'Level Funded Supplier Payment Cycle'),
    ('CHR - SF',    'Curative Subscriber Payment Cycle'),
    ('CHR - SF',    'Curative Supplier Payment Cycle')
ON CONFLICT DO NOTHING;
