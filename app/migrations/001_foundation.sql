CREATE TABLE instrument_versions (
    instrument_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    symbol TEXT NOT NULL,
    event_time TEXT NOT NULL,
    available_at TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (instrument_id, provider, feed, version)
);
CREATE INDEX idx_instrument_temporal ON instrument_versions(available_at, event_time);
CREATE VIRTUAL TABLE knowledge_index USING fts5(source_id UNINDEXED, title, body);
CREATE TABLE health_probe (id INTEGER PRIMARY KEY);
