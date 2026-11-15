BEGIN;
SET LOCAL search_path TO social_wars, pg_catalog;
CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY, author TEXT NOT NULL REFERENCES accounts(username),
        body TEXT NOT NULL, created BIGINT NOT NULL
    );
CREATE INDEX IF NOT EXISTS chat_created ON chat_messages(created, id);
CREATE TABLE IF NOT EXISTS friendships (
        first TEXT NOT NULL REFERENCES accounts(username),
        second TEXT NOT NULL REFERENCES accounts(username),
        sender TEXT NOT NULL REFERENCES accounts(username),
        accepted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(first, second)
    );
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_messages, friendships TO social_wars_game;
COMMIT;
