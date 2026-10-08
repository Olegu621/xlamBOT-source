CREATE TABLE installations(id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, created REAL NOT NULL);
CREATE TABLE rate(key TEXT PRIMARY KEY, bucket INTEGER NOT NULL, count INTEGER NOT NULL);
CREATE TABLE events(installation TEXT, id TEXT, fingerprint TEXT, count INTEGER, level TEXT, code TEXT, version TEXT, revision INTEGER, exception TEXT, stage TEXT, trace TEXT, seen REAL, PRIMARY KEY(installation,id));
CREATE INDEX events_fingerprint ON events(fingerprint);
CREATE INDEX events_seen ON events(seen);
CREATE TABLE groups(fingerprint TEXT PRIMARY KEY, total INTEGER DEFAULT 0, priority INTEGER DEFAULT 0, notified INTEGER DEFAULT 0, last_sent REAL DEFAULT 0, retry_at REAL DEFAULT 0, failures INTEGER DEFAULT 0);
CREATE INDEX groups_due ON groups((total>notified),retry_at,last_sent);
CREATE TRIGGER event_insert AFTER INSERT ON events BEGIN
  INSERT INTO groups(fingerprint,total,priority) VALUES(NEW.fingerprint,NEW.count,CASE NEW.level WHEN 'critical' THEN 3 WHEN 'error' THEN 2 ELSE 1 END)
    ON CONFLICT(fingerprint) DO UPDATE SET total=total+NEW.count;
END;
CREATE TRIGGER event_update AFTER UPDATE OF count ON events BEGIN
  UPDATE groups SET total=total+NEW.count-OLD.count WHERE fingerprint=NEW.fingerprint;
END;
CREATE TABLE delivery_lock(id INTEGER PRIMARY KEY CHECK(id=1), lease TEXT, until REAL DEFAULT 0);
INSERT INTO delivery_lock(id) VALUES(1);
