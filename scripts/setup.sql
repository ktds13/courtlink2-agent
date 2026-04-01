-- CourtLink2 Agent - PostgreSQL + pgvector setup
-- Run this once against your PostgreSQL instance before using the agent.
--
-- Usage:
--   psql -U postgres -d courtlink2_agent -f scripts/setup.sql
-- Or create the DB first:
--   psql -U postgres -c "CREATE DATABASE courtlink2_agent;"
--   psql -U postgres -d courtlink2_agent -f scripts/setup.sql

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table for vectorized CourtLink2 documentation
-- Each row is one markdown section (H2 or H3 heading + content)
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- e.g. 'SmartClient.md', 'Management.md', 'CCM.md'
    section     TEXT NOT NULL,          -- e.g. 'MQTT Topics', 'REST API Reference'
    content     TEXT NOT NULL,          -- full text of the section
    embedding   vector(1536),           -- OpenAI text-embedding-3-small output
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast approximate nearest-neighbour search
-- cosine distance matches the normalised OpenAI embedding space
CREATE INDEX IF NOT EXISTS documents_embedding_idx
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Optional: index on source for filtered queries
CREATE INDEX IF NOT EXISTS documents_source_idx ON documents (source);

-- Code chunks table for vectorized CourtLink2 source code
-- Each row is one logical chunk of source code (file, class, or method)
CREATE TABLE IF NOT EXISTS code_chunks (
    id          SERIAL PRIMARY KEY,
    file_path   TEXT NOT NULL,      -- relative path from repo root, e.g. 'CourtLink2.CCM/ViewModel/MeetingViewModel.cs'
    project     TEXT NOT NULL,      -- e.g. 'CourtLink2.CCM', 'CourtLink2.Management'
    chunk_name  TEXT NOT NULL,      -- e.g. 'MeetingViewModel.cs', 'class DeviceItemViewModel'
    language    TEXT NOT NULL,      -- 'csharp', 'xaml', 'json', 'cpp', 'xml'
    content     TEXT NOT NULL,      -- actual source code text
    embedding   vector(1536),       -- OpenAI text-embedding-ada-002 output
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search over code
CREATE INDEX IF NOT EXISTS code_chunks_embedding_idx
    ON code_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- B-tree indexes for filtered queries (by project or language)
CREATE INDEX IF NOT EXISTS code_chunks_file_path_idx ON code_chunks (file_path);
CREATE INDEX IF NOT EXISTS code_chunks_project_idx   ON code_chunks (project);
CREATE INDEX IF NOT EXISTS code_chunks_language_idx  ON code_chunks (language);

-- File descriptions table — one row per source file, LLM-generated description + embedding
-- Used by search_file_descriptions tool so the agent can locate files by semantic intent
-- before opening them with read_file.
CREATE TABLE IF NOT EXISTS file_descriptions (
    id          SERIAL PRIMARY KEY,
    file_path   TEXT NOT NULL UNIQUE,   -- relative path from repo root, e.g. 'CourtLink2.CCM/ViewModels/MeetingViewModel.cs'
    project     TEXT NOT NULL,          -- e.g. 'CourtLink2.CCM', 'CourtLink2.Management'
    language    TEXT NOT NULL,          -- 'csharp', 'xaml', 'json', 'cpp', 'xml'
    description TEXT NOT NULL,          -- LLM-generated natural language description of the file
    embedding   vector(1536),           -- embedding of the description (text-embedding-ada-002)
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search over descriptions
CREATE INDEX IF NOT EXISTS file_descriptions_embedding_idx
    ON file_descriptions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- B-tree indexes for filtered queries
CREATE INDEX IF NOT EXISTS file_descriptions_project_idx  ON file_descriptions (project);
CREATE INDEX IF NOT EXISTS file_descriptions_language_idx ON file_descriptions (language);

-- Conversation memory table for multi-turn sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    messages    JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at on chat_sessions
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
