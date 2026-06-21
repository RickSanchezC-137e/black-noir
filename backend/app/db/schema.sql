-- Noir core SQLite schema (08_conventions §6). SQLite only; vectors live in ChromaDB.

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    title       TEXT,
    meta        TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content     TEXT NOT NULL,
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','done','error','cancelled')),
    payload     TEXT,
    result      TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, created_at);

CREATE TABLE IF NOT EXISTS modules (
    name        TEXT PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'idle',   -- idle|busy|error|offline
    config      TEXT,
    namespace   TEXT,
    manifest    TEXT,
    version     TEXT,
    updated_at  TEXT NOT NULL
);

-- Immutable audit log (Governor). Insert-only.
CREATE TABLE IF NOT EXISTS agent_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    module       TEXT,
    tool         TEXT,
    args         TEXT,
    decision     TEXT,        -- ALLOW|CONFIRM|DENY|KILL
    action_class TEXT,        -- read|local_write|external_send|money|system|self_modify
    reason       TEXT,
    ok           INTEGER NOT NULL,
    duration_ms  INTEGER,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agentlog_module ON agent_log(module, created_at);

-- Self-improvement contour (C4, 09_self_improvement.md §12), si_ namespace
CREATE TABLE IF NOT EXISTS si_hypotheses (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL,
    domain TEXT NOT NULL, intent TEXT NOT NULL, summary TEXT NOT NULL, evidence TEXT,
    impact REAL, confidence REAL, cost REAL, priority REAL, signature TEXT NOT NULL,
    contour TEXT NOT NULL, status TEXT NOT NULL, experiment_id TEXT, verdict_id TEXT,
    archived_reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_si_hyp_signature ON si_hypotheses(signature);
CREATE TABLE IF NOT EXISTS si_experiments (
    id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL, domain TEXT NOT NULL,
    constitution TEXT NOT NULL, eval TEXT NOT NULL, status TEXT NOT NULL,
    started_at TEXT, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS si_verdicts (
    id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, decision TEXT NOT NULL, contour TEXT NOT NULL,
    constitution_passed INTEGER NOT NULL, governor TEXT NOT NULL, quality_gate TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS si_versions (
    domain TEXT NOT NULL, version INTEGER NOT NULL, experiment_id TEXT,
    rollback_token TEXT NOT NULL UNIQUE, active INTEGER NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (domain, version)
);
CREATE TABLE IF NOT EXISTS si_budget_ledger (
    day TEXT PRIMARY KEY, tokens_limit INTEGER NOT NULL, requests_limit INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0, requests_used INTEGER NOT NULL DEFAULT 0,
    builder_runs INTEGER NOT NULL DEFAULT 0, adopt_clones INTEGER NOT NULL DEFAULT 0,
    paused INTEGER NOT NULL DEFAULT 0
);
-- adoption registry mirror (verdicts also written to 11_adoption.md)
CREATE TABLE IF NOT EXISTS si_adoptions (
    repo TEXT PRIMARY KEY, capability TEXT, cluster TEXT, verdict TEXT, license TEXT,
    security TEXT, eval TEXT, status TEXT, decided_at TEXT
);

-- Ideas (C4 idea bot / generator)
CREATE TABLE IF NOT EXISTS ideas (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',   -- new|review|backlog|active|done|rejected|cold
    score       REAL,
    created_at  TEXT NOT NULL
);

-- Episodic memory (CANON §10: episodic -> SQLite). Vector lives in Chroma via chroma_id.
CREATE TABLE IF NOT EXISTS episodic (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    source      TEXT,         -- telegram|voice|desktop|system|chat
    role        TEXT,         -- user|noir|tool
    content     TEXT NOT NULL,
    chroma_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodic_ts ON episodic(ts);
