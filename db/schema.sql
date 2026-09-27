-- NeedToKnow schema (Step 2)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id    TEXT PRIMARY KEY,          -- e.g. 'riya'
    name  TEXT NOT NULL,
    role  TEXT NOT NULL
);

CREATE TABLE groups (
    id TEXT PRIMARY KEY              -- e.g. 'marketing'
);

-- Who belongs to which group (many-to-many)
CREATE TABLE user_groups (
    user_id  TEXT REFERENCES users(id)  ON DELETE CASCADE,
    group_id TEXT REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
);

CREATE TABLE documents (
    id         TEXT PRIMARY KEY,     -- e.g. 'wiki-atlas'
    title      TEXT NOT NULL,
    department TEXT NOT NULL,        -- hr | finance | wiki (later: which MCP server owns it)
    updated_at DATE
);

-- One row per section. This is the unit we search and protect.
CREATE TABLE chunks (
    id        SERIAL PRIMARY KEY,
    doc_id    TEXT REFERENCES documents(id) ON DELETE CASCADE,
    section   TEXT NOT NULL,
    content   TEXT NOT NULL,
    embedding vector(384),         -- the meaning of the text, as 384 numbers
    tsv       tsvector GENERATED ALWAYS AS
              (to_tsvector('english', section || ' ' || content)) STORED   -- keywords, for keyword search
);

CREATE INDEX chunks_tsv_idx ON chunks USING GIN (tsv);

-- Which groups may read which chunk. No rows = nobody can read it (deny by default).
CREATE TABLE chunk_acl (
    chunk_id INT  REFERENCES chunks(id)  ON DELETE CASCADE,
    group_id TEXT REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (chunk_id, group_id)
);