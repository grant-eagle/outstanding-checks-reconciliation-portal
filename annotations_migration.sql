-- Run this in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS discrepancy_annotations (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    subsidiary       TEXT        NOT NULL,
    discrepancy_type TEXT        NOT NULL,
    check_number     TEXT        NOT NULL,
    next_steps       TEXT        DEFAULT '',
    notes            TEXT        DEFAULT '',
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(subsidiary, discrepancy_type, check_number)
);

ALTER TABLE discrepancy_annotations ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON discrepancy_annotations TO anon;

CREATE POLICY "annotations_select" ON discrepancy_annotations FOR SELECT TO anon USING (true);
CREATE POLICY "annotations_insert" ON discrepancy_annotations FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "annotations_update" ON discrepancy_annotations FOR UPDATE TO anon USING (true) WITH CHECK (true);
