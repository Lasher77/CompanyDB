-- Migration: Add contact fields to company table
-- Date: 2026-01-10
-- Description: Adds email, website, phone, and domain columns to align with updated Company model

BEGIN;

-- Add contact fields to company table
ALTER TABLE company
ADD COLUMN IF NOT EXISTS email TEXT,
ADD COLUMN IF NOT EXISTS website TEXT,
ADD COLUMN IF NOT EXISTS phone TEXT,
ADD COLUMN IF NOT EXISTS domain TEXT;

-- Add index on domain for faster searches
CREATE INDEX IF NOT EXISTS ix_company_domain ON company(domain);

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 001 completed: Added email, website, phone, domain columns to company table';
END $$;

COMMIT;
