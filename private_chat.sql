BEGIN;
SET LOCAL search_path TO social_wars, pg_catalog;
CREATE TABLE IF NOT EXISTS private_messages (
        id TEXT PRIMARY KEY, first TEXT NOT NULL REFERENCES accounts(username),
        second TEXT NOT NULL REFERENCES accounts(username),
        author TEXT NOT NULL REFERENCES accounts(username), body TEXT NOT NULL, created BIGINT NOT NULL
    );
CREATE INDEX IF NOT EXISTS private_chat_created ON private_messages(first, second, created, id);
GRANT SELECT, INSERT ON private_messages TO social_wars_game;
COMMIT;
