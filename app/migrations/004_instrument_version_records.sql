CREATE TABLE instrument_version_records (
    instrument_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    symbol TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    event_time TEXT NOT NULL,
    published_at TEXT,
    source_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (instrument_id, provider, feed, version),
    FOREIGN KEY (instrument_id, provider, feed, version)
        REFERENCES instrument_versions(instrument_id, provider, feed, version),
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (received_at <= processed_at AND processed_at <= available_at),
    CHECK (source_timestamp <= available_at),
    CHECK (published_at IS NULL OR published_at <= available_at)
);
CREATE INDEX idx_instrument_version_records_pit
    ON instrument_version_records(instrument_id, provider, feed, available_at, valid_from);
