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
