-- Indexes for observatory.db
-- Source of truth: blueprint/02-schema.md

CREATE INDEX IF NOT EXISTS idx_datasets_portal ON datasets(portal_id);
CREATE INDEX IF NOT EXISTS idx_datasets_action ON datasets(max_action_code, rejected);
CREATE INDEX IF NOT EXISTS idx_runs_dataset ON runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_runs_action ON runs(dataset_id, action);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_joins_status ON proposed_joins(status);
CREATE INDEX IF NOT EXISTS idx_scan_catalog_status ON scan_catalog(portal_id, status);
CREATE INDEX IF NOT EXISTS idx_scan_catalog_format ON scan_catalog(format, size_bytes);
CREATE INDEX IF NOT EXISTS idx_scan_progress_portal ON scan_progress(portal_id);
