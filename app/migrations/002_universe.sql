CREATE TABLE source_ingestions (
    ingestion_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    source_name TEXT NOT NULL,
    raw_path TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-fA-F]*'),
    source_timestamp TEXT,
    received_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'SUCCESS', 'DEGRADED', 'FAILED')),
    CHECK (received_at <= processed_at AND processed_at <= available_at)
);
CREATE INDEX idx_source_ingestions_provider_feed_available ON source_ingestions(provider, feed, available_at);
CREATE INDEX idx_source_ingestions_sha256 ON source_ingestions(sha256);

CREATE TABLE universe_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    as_of TEXT NOT NULL,
    event_time TEXT NOT NULL,
    published_at TEXT,
    source_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    source_ingestion_id TEXT NOT NULL,
    FOREIGN KEY (source_ingestion_id) REFERENCES source_ingestions(ingestion_id),
    CHECK (received_at <= processed_at AND processed_at <= available_at),
    CHECK (source_timestamp <= available_at),
    CHECK (published_at IS NULL OR published_at <= available_at)
);
CREATE INDEX idx_universe_snapshots_lookup ON universe_snapshots(provider, feed, as_of, available_at);
CREATE INDEX idx_universe_snapshots_source_ingestion ON universe_snapshots(source_ingestion_id);

CREATE TABLE universe_snapshot_members (
    snapshot_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    instrument_version INTEGER NOT NULL CHECK (instrument_version >= 1),
    symbol TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, instrument_id),
    FOREIGN KEY (snapshot_id) REFERENCES universe_snapshots(snapshot_id),
    FOREIGN KEY (instrument_id, provider, feed, instrument_version)
        REFERENCES instrument_versions(instrument_id, provider, feed, version)
);
CREATE INDEX idx_universe_snapshot_members_instrument ON universe_snapshot_members(instrument_id);
CREATE INDEX idx_universe_snapshot_members_symbol ON universe_snapshot_members(provider, feed, symbol);
