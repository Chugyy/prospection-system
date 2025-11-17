-- Migration: Add about and location fields to prospects table
-- Date: 2025-11-15

ALTER TABLE prospects
ADD COLUMN IF NOT EXISTS about TEXT,
ADD COLUMN IF NOT EXISTS location VARCHAR;

COMMENT ON COLUMN prospects.about IS 'LinkedIn profile about/description section (bio)';
COMMENT ON COLUMN prospects.location IS 'LinkedIn profile location/city';
