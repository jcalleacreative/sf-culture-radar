# backend/db/models.py

CREATE_STORIES_TABLE = """
CREATE TABLE IF NOT EXISTS stories (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    url              TEXT NOT NULL UNIQUE,
    source           TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    upvotes          INTEGER,
    comments         INTEGER,
    llm_score        REAL,
    popularity_score REAL,
    category         TEXT,
    explanation      TEXT,
    signals          TEXT
);
"""

# Run after CREATE TABLE to add columns introduced after initial schema.
MIGRATIONS = [
    "ALTER TABLE stories ADD COLUMN signals TEXT",
]
