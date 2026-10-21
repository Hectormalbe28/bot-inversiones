CREATE TABLE operational_universe_snapshots (
    operational_snapshot_id TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
    generated_at TEXT NOT NULL,
    PRIMARY KEY (operational_snapshot_id),
    UNIQUE (source_snapshot_id, policy_id, policy_version),
    FOREIGN KEY (source_snapshot_id) REFERENCES universe_snapshots(snapshot_id)
);

CREATE TABLE operational_universe_members (
    operational_snapshot_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    included INTEGER NOT NULL CHECK (included IN (0, 1)),
    reason_code TEXT,
    PRIMARY KEY (operational_snapshot_id, instrument_id),
    FOREIGN KEY (operational_snapshot_id)
        REFERENCES operational_universe_snapshots(operational_snapshot_id),
    CHECK ((included = 1 AND reason_code IS NULL) OR (included = 0 AND reason_code IS NOT NULL))
);
CREATE INDEX idx_operational_universe_source
    ON operational_universe_snapshots(source_snapshot_id, policy_id, policy_version);
