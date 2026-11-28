-- Migration 0042: drop legacy_status column
ALTER TABLE orders DROP COLUMN legacy_status;
