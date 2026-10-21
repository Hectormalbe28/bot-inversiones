CREATE TABLE symbol_alias_versions (
    instrument_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    symbol TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    event_time TEXT NOT NULL,
    published_at TEXT,
    source_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (instrument_id, provider, feed, symbol, valid_from, version),
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (received_at <= processed_at AND processed_at <= available_at),
    CHECK (source_timestamp <= available_at),
    CHECK (published_at IS NULL OR published_at <= available_at)
);
CREATE INDEX idx_symbol_alias_pit_lookup
    ON symbol_alias_versions(provider, feed, symbol, available_at, valid_from);

CREATE TABLE ingestion_results (
    result_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    source_name TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('FETCH', 'PARSE', 'NORMALIZE', 'IDENTITY', 'QUALITY', 'SNAPSHOT')),
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'QUARANTINED')),
    reason_code TEXT,
    sha256 TEXT CHECK (sha256 IS NULL OR (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-fA-F]*')),
    raw_path TEXT,
    source_timestamp TEXT,
    received_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    record_count INTEGER CHECK (record_count IS NULL OR record_count >= 0),
    CHECK (received_at <= processed_at AND processed_at <= available_at),
    CHECK (source_timestamp IS NULL OR source_timestamp <= available_at),
    CHECK ((sha256 IS NULL AND raw_path IS NULL) OR (sha256 IS NOT NULL AND raw_path IS NOT NULL))
);
CREATE INDEX idx_ingestion_results_source
    ON ingestion_results(provider, feed, source_name, available_at);
