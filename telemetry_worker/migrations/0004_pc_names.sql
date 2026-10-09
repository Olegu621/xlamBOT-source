CREATE TABLE IF NOT EXISTS installation_names (
  installation TEXT PRIMARY KEY REFERENCES installations(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT ''
);
