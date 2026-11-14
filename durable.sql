CREATE SCHEMA IF NOT EXISTS social_wars;
REVOKE ALL ON SCHEMA social_wars FROM PUBLIC;
CREATE TABLE IF NOT EXISTS social_wars.accounts (
    username text PRIMARY KEY CHECK (username=lower(username)),
    password text NOT NULL,
    save_id text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS social_wars.sessions (
    token_hash text PRIMARY KEY,
    username text NOT NULL REFERENCES social_wars.accounts(username),
    expires bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS social_wars.auth_attempts (
    kind text NOT NULL, address text NOT NULL, attempted bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_attempt_time ON social_wars.auth_attempts(attempted);
CREATE TABLE IF NOT EXISTS social_wars.game_files (
    path text PRIMARY KEY, data jsonb NOT NULL
);
