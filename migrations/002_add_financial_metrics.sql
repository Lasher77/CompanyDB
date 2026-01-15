-- Migration: Add employee_count and last_revenue columns to company table
-- These columns are extracted from full_record for fast filtering

-- Add new columns
ALTER TABLE company ADD COLUMN IF NOT EXISTS employee_count INTEGER;
ALTER TABLE company ADD COLUMN IF NOT EXISTS last_revenue DOUBLE PRECISION;

-- Create indexes for fast range queries
CREATE INDEX IF NOT EXISTS ix_company_employee_count ON company (employee_count) WHERE employee_count IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_company_last_revenue ON company (last_revenue) WHERE last_revenue IS NOT NULL;

-- Composite index for common filter combinations
CREATE INDEX IF NOT EXISTS ix_company_city_employees ON company (address_city, employee_count) WHERE address_city IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_company_postal_employees ON company (address_postal_code, employee_count) WHERE address_postal_code IS NOT NULL;
