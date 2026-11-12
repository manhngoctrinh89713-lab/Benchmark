-- Columns moved to settlement_entries.
ALTER TABLE orders DROP COLUMN source_channel;
ALTER TABLE orders DROP COLUMN wms_ref;
