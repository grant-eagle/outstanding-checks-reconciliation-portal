-- ============================================================
-- Check Reconciliation Portal — Complete Database Setup
-- Safe to run multiple times from a single SQL Editor tab.
-- ============================================================


-- ── issued_checks ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS issued_checks (
    id           UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    payment_date DATE           NOT NULL,
    check_number TEXT           NOT NULL,
    amount       NUMERIC(14,2)  NOT NULL,
    subsidiary   TEXT,
    uploaded_at  TIMESTAMPTZ    DEFAULT NOW()
);
ALTER TABLE issued_checks ADD COLUMN IF NOT EXISTS subsidiary TEXT;
CREATE INDEX IF NOT EXISTS idx_issued_check_number ON issued_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_issued_subsidiary   ON issued_checks(subsidiary);
ALTER TABLE issued_checks ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON issued_checks TO anon;
DROP POLICY IF EXISTS "issued_select" ON issued_checks;
CREATE POLICY "issued_select" ON issued_checks FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "issued_insert" ON issued_checks;
CREATE POLICY "issued_insert" ON issued_checks FOR INSERT TO anon WITH CHECK (true);


-- ── cleared_checks ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cleared_checks (
    id           UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    date         DATE           NOT NULL,
    description  TEXT,
    check_number TEXT           NOT NULL,
    status       TEXT,
    amount       NUMERIC(14,2)  NOT NULL,
    subsidiary   TEXT,
    uploaded_at  TIMESTAMPTZ    DEFAULT NOW()
);
ALTER TABLE cleared_checks ADD COLUMN IF NOT EXISTS subsidiary TEXT;
CREATE INDEX IF NOT EXISTS idx_cleared_check_number ON cleared_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_cleared_subsidiary   ON cleared_checks(subsidiary);
ALTER TABLE cleared_checks ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON cleared_checks TO anon;
DROP POLICY IF EXISTS "cleared_select" ON cleared_checks;
CREATE POLICY "cleared_select" ON cleared_checks FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "cleared_insert" ON cleared_checks;
CREATE POLICY "cleared_insert" ON cleared_checks FOR INSERT TO anon WITH CHECK (true);


-- ── seed_checks ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS seed_checks (
    id           UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    check_number TEXT           NOT NULL,
    payment_date DATE           NOT NULL,
    amount       NUMERIC(14,2)  NOT NULL,
    subsidiary   TEXT           NOT NULL,
    uploaded_at  TIMESTAMPTZ    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_seed_check_number ON seed_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_seed_subsidiary   ON seed_checks(subsidiary);
ALTER TABLE seed_checks ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON seed_checks TO anon;
DROP POLICY IF EXISTS "seed_select" ON seed_checks;
CREATE POLICY "seed_select" ON seed_checks FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "seed_insert" ON seed_checks;
CREATE POLICY "seed_insert" ON seed_checks FOR INSERT TO anon WITH CHECK (true);


-- ── voided_checks ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voided_checks (
    id           UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    payment_date DATE           NOT NULL,
    check_number TEXT           NOT NULL,
    amount       NUMERIC(14,2)  NOT NULL,
    subsidiary   TEXT           NOT NULL,
    uploaded_at  TIMESTAMPTZ    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_voided_check_number ON voided_checks(check_number);
CREATE INDEX IF NOT EXISTS idx_voided_subsidiary   ON voided_checks(subsidiary);
ALTER TABLE voided_checks ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON voided_checks TO anon;
DROP POLICY IF EXISTS "voided_select" ON voided_checks;
CREATE POLICY "voided_select" ON voided_checks FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "voided_insert" ON voided_checks;
CREATE POLICY "voided_insert" ON voided_checks FOR INSERT TO anon WITH CHECK (true);


-- ── subsidiary_cycles ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS subsidiary_cycles (
    id               UUID  DEFAULT gen_random_uuid() PRIMARY KEY,
    subsidiary       TEXT  NOT NULL,
    cycle_identifier TEXT  NOT NULL,
    UNIQUE(subsidiary, cycle_identifier)
);
ALTER TABLE subsidiary_cycles ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON subsidiary_cycles TO anon;
DROP POLICY IF EXISTS "cycles_select" ON subsidiary_cycles;
CREATE POLICY "cycles_select" ON subsidiary_cycles FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "cycles_insert" ON subsidiary_cycles;
CREATE POLICY "cycles_insert" ON subsidiary_cycles FOR INSERT TO anon WITH CHECK (true);
INSERT INTO subsidiary_cycles (subsidiary, cycle_identifier) VALUES
    ('CIC - FF',    'Fully Insured Subscriber Payment Cycle'),
    ('CIC - FF',    'Fully Insured Supplier Payment Cycle'),
    ('CAdmin - LF', 'Level Funded EPOValue Supplier Payment Cycle'),
    ('CAdmin - LF', 'Level Funded Subscriber Payment Cycle'),
    ('CAdmin - LF', 'Level Funded Supplier Payment Cycle'),
    ('CHR - SF',    'Curative Subscriber Payment Cycle'),
    ('CHR - SF',    'Curative Supplier Payment Cycle')
ON CONFLICT DO NOTHING;


-- ── issued_ach ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS issued_ach (
    id           UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    payment_date DATE           NOT NULL,
    amount       NUMERIC(14,2)  NOT NULL,
    subsidiary   TEXT           NOT NULL,
    uploaded_at  TIMESTAMPTZ    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_issued_ach_date       ON issued_ach(payment_date);
CREATE INDEX IF NOT EXISTS idx_issued_ach_subsidiary ON issued_ach(subsidiary);
ALTER TABLE issued_ach ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON issued_ach TO anon;
DROP POLICY IF EXISTS "issued_ach_select" ON issued_ach;
CREATE POLICY "issued_ach_select" ON issued_ach FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "issued_ach_insert" ON issued_ach;
CREATE POLICY "issued_ach_insert" ON issued_ach FOR INSERT TO anon WITH CHECK (true);


-- ── cleared_ach ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cleared_ach (
    id           UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    date         DATE           NOT NULL,
    amount       NUMERIC(14,2)  NOT NULL,
    subsidiary   TEXT           NOT NULL,
    uploaded_at  TIMESTAMPTZ    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cleared_ach_date       ON cleared_ach(date);
CREATE INDEX IF NOT EXISTS idx_cleared_ach_subsidiary ON cleared_ach(subsidiary);
ALTER TABLE cleared_ach ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON cleared_ach TO anon;
DROP POLICY IF EXISTS "cleared_ach_select" ON cleared_ach;
CREATE POLICY "cleared_ach_select" ON cleared_ach FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "cleared_ach_insert" ON cleared_ach;
CREATE POLICY "cleared_ach_insert" ON cleared_ach FOR INSERT TO anon WITH CHECK (true);


-- ── discrepancy_annotations ───────────────────────────────
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
DROP POLICY IF EXISTS "annotations_select" ON discrepancy_annotations;
CREATE POLICY "annotations_select" ON discrepancy_annotations FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "annotations_insert" ON discrepancy_annotations;
CREATE POLICY "annotations_insert" ON discrepancy_annotations FOR INSERT TO anon WITH CHECK (true);
DROP POLICY IF EXISTS "annotations_update" ON discrepancy_annotations;
CREATE POLICY "annotations_update" ON discrepancy_annotations FOR UPDATE TO anon USING (true) WITH CHECK (true);


-- ── subsidiary_accounts ───────────────────────────────────
CREATE TABLE IF NOT EXISTS subsidiary_accounts (
    id             UUID  DEFAULT gen_random_uuid() PRIMARY KEY,
    subsidiary     TEXT  NOT NULL,
    account_number TEXT  NOT NULL,
    UNIQUE(subsidiary, account_number)
);
ALTER TABLE subsidiary_accounts ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON subsidiary_accounts TO anon;
DROP POLICY IF EXISTS "accounts_select" ON subsidiary_accounts;
CREATE POLICY "accounts_select" ON subsidiary_accounts FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "accounts_insert" ON subsidiary_accounts;
CREATE POLICY "accounts_insert" ON subsidiary_accounts FOR INSERT TO anon WITH CHECK (true);
INSERT INTO subsidiary_accounts (subsidiary, account_number) VALUES
    ('CIC - FF',    '26830036'),
    ('CAdmin - LF', '26833523'),
    ('CHR - SF',    '26838851')
ON CONFLICT DO NOTHING;


-- ── audit_log ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    email        TEXT        NOT NULL,
    display_name TEXT        NOT NULL DEFAULT '',
    action       TEXT        NOT NULL,
    details      TEXT        DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON audit_log TO anon;
DROP POLICY IF EXISTS "audit_select" ON audit_log;
CREATE POLICY "audit_select" ON audit_log FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "audit_insert" ON audit_log;
CREATE POLICY "audit_insert" ON audit_log FOR INSERT TO anon WITH CHECK (true);


-- ── user_profiles ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_profiles (
    email        TEXT        PRIMARY KEY,
    display_name TEXT        NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE ON user_profiles TO anon;
DROP POLICY IF EXISTS "profiles_select" ON user_profiles;
CREATE POLICY "profiles_select" ON user_profiles FOR SELECT TO anon USING (true);
DROP POLICY IF EXISTS "profiles_insert" ON user_profiles;
CREATE POLICY "profiles_insert" ON user_profiles FOR INSERT TO anon WITH CHECK (true);
DROP POLICY IF EXISTS "profiles_update" ON user_profiles;
CREATE POLICY "profiles_update" ON user_profiles FOR UPDATE TO anon USING (true) WITH CHECK (true);
