-- NexusAC website schema. Runs inside Supabase Postgres (public schema, nx_ prefix
-- so everything is visible in the Supabase table editor without colliding with
-- anything else the project holds).
--
-- RLS is enabled with no policies on every table: the website connects as the
-- database owner and bypasses RLS, while anyone holding only the publishable
-- (anon) key gets nothing back from PostgREST. Do not add permissive policies.

CREATE TABLE IF NOT EXISTS nx_users (
    id         uuid PRIMARY KEY,                 -- Supabase auth.users.id
    email      text UNIQUE NOT NULL,
    name       text NOT NULL,
    created    bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS nx_workspaces (
    id         uuid PRIMARY KEY,
    name       text NOT NULL,
    created    bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS nx_members (
    workspace  uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    user_id    uuid NOT NULL REFERENCES nx_users(id) ON DELETE CASCADE,
    role       text NOT NULL CHECK (role IN ('owner','administrator','moderator','viewer')),
    PRIMARY KEY (workspace, user_id)
);

CREATE TABLE IF NOT EXISTS nx_sessions (
    hash       text PRIMARY KEY,                 -- sha256 of the cookie value
    user_id    uuid NOT NULL REFERENCES nx_users(id) ON DELETE CASCADE,
    workspace  uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    expires    bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS nx_sessions_expires ON nx_sessions(expires);

-- One row per FiveM server. token_hash is the sha256 of the 43-character API key
-- handed to the operator; the key itself is never stored.
CREATE TABLE IF NOT EXISTS nx_servers (
    id           uuid PRIMARY KEY,
    workspace    uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    name         text NOT NULL,
    token_hash   text UNIQUE NOT NULL,
    token_hint   text NOT NULL DEFAULT '',       -- first 6 chars, so a key is recognisable in the UI
    created      bigint NOT NULL,
    last_seen    bigint,
    snapshot     jsonb,
    boot         text,
    sequence     bigint NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS nx_servers_workspace ON nx_servers(workspace, created);

-- Every resource start produces a new boot id. Retiring them here means a replayed
-- snapshot from an old session cannot resurrect a stale view.
CREATE TABLE IF NOT EXISTS nx_bridge_boots (
    server     uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    boot       text NOT NULL,
    at         bigint NOT NULL,
    PRIMARY KEY (server, boot)
);

CREATE TABLE IF NOT EXISTS nx_commands (
    id         uuid PRIMARY KEY,
    server     uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    actor      uuid NOT NULL,
    actor_name text NOT NULL,
    body       jsonb NOT NULL,
    created    bigint NOT NULL,
    expires    bigint NOT NULL,
    status     text NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending','sent','succeeded','failed','uncertain','expired','cancelled')),
    result     text,
    ack_at     bigint
);
CREATE INDEX IF NOT EXISTS nx_commands_server ON nx_commands(server, created DESC);

CREATE TABLE IF NOT EXISTS nx_evidence (
    server     uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    id         text NOT NULL,
    body       jsonb NOT NULL,
    updated    bigint NOT NULL,
    PRIMARY KEY (server, id)
);
CREATE INDEX IF NOT EXISTS nx_evidence_updated ON nx_evidence(server, updated DESC);

CREATE TABLE IF NOT EXISTS nx_media (
    server      uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    evidence_id text NOT NULL,
    slot        int NOT NULL CHECK (slot BETWEEN 0 AND 2),
    data        text NOT NULL,
    created     bigint NOT NULL,
    PRIMARY KEY (server, evidence_id, slot)
);

CREATE TABLE IF NOT EXISTS nx_audit (
    id         uuid PRIMARY KEY,
    workspace  uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    actor      text NOT NULL,
    action     text NOT NULL,
    detail     text NOT NULL,
    at         bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS nx_audit_workspace ON nx_audit(workspace, at DESC);

CREATE TABLE IF NOT EXISTS nx_invites (
    hash       text PRIMARY KEY,
    workspace  uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    role       text NOT NULL CHECK (role IN ('administrator','moderator','viewer')),
    expires    bigint NOT NULL,
    created_by uuid NOT NULL
);

CREATE TABLE IF NOT EXISTS nx_limits (
    key        text PRIMARY KEY,
    count      int NOT NULL,
    expires    bigint NOT NULL
);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['nx_users','nx_workspaces','nx_members','nx_sessions','nx_servers',
                             'nx_bridge_boots','nx_commands','nx_evidence','nx_media','nx_audit',
                             'nx_invites','nx_limits']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON TABLE %I FROM anon, authenticated', t);
    END LOOP;
END $$;
