CREATE TABLE installation_platforms(installation TEXT PRIMARY KEY NOT NULL, platform TEXT NOT NULL CHECK(platform IN ('pc','android')));
