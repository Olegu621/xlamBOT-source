CREATE TABLE stats_devices(installation TEXT NOT NULL, device TEXT NOT NULL, active INTEGER NOT NULL, paused INTEGER NOT NULL, revision INTEGER NOT NULL, seen REAL NOT NULL, PRIMARY KEY(installation,device));
CREATE INDEX stats_devices_seen ON stats_devices(seen);
CREATE TABLE stats_matches(installation TEXT NOT NULL, id TEXT NOT NULL, played REAL NOT NULL, result TEXT NOT NULL, delta INTEGER, source TEXT NOT NULL, PRIMARY KEY(installation,id));
CREATE INDEX stats_matches_played ON stats_matches(played);
CREATE TABLE telegram_updates(id INTEGER PRIMARY KEY, lease REAL NOT NULL, done INTEGER DEFAULT 0);
