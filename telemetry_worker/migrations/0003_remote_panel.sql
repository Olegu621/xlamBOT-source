CREATE TABLE remote_links(installation TEXT PRIMARY KEY, user_id TEXT, key_hash TEXT UNIQUE, expires REAL DEFAULT 0);
CREATE TABLE mini_sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
CREATE INDEX mini_sessions_expiry ON mini_sessions(expires);
CREATE TABLE mini_grants(token TEXT PRIMARY KEY, user_id TEXT NOT NULL, installation TEXT NOT NULL, expires REAL NOT NULL);
CREATE INDEX mini_grants_expiry ON mini_grants(expires);
CREATE TABLE panel_versions(installation TEXT PRIMARY KEY, revision INTEGER, seen REAL);
CREATE TABLE panel_activity(id INTEGER PRIMARY KEY AUTOINCREMENT, installation TEXT, kind TEXT, revision INTEGER DEFAULT 0, seen REAL);
CREATE INDEX panel_activity_seen ON panel_activity(seen);
