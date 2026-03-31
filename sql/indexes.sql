-- Indexes for observatory.db
-- Source of truth: blueprint/02-schema.md

CREATE INDEX IF NOT EXISTS idx_datasets_portal ON datasets(portal_id);
CREATE INDEX IF NOT EXISTS idx_datasets_action ON datasets(max_action_code, rejected);
CREATE INDEX IF NOT EXISTS idx_runs_dataset ON runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_runs_action ON runs(dataset_id, action);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_joins_status ON proposed_joins(status);
