-- Identities: the account-linking store behind the Identities page.
--
-- The anti-cheat already keeps this shape in its own MariaDB (see
-- NexusAC/server/sv_identity.lua), but that database is on the game server and
-- this website cannot reach it. So the resource mirrors it up over the existing
-- bridge in small batches and it lands here.
--
-- Scoped to the WORKSPACE, not to one server. A player who connects to three
-- servers in the same workspace is one identity with marks from all three,
-- which is the whole point: alias hunting across a group of servers is exactly
-- the case the page exists for.
--
-- Linking is deliberately NOT materialised into an edge table. Two identities
-- are linked when they share a (kind, value) mark, so the graph is derived at
-- query time from nx_identity_marks. An edge table would have to be rebuilt on
-- every mark that arrives and would be wrong the moment it fell behind.

CREATE TABLE IF NOT EXISTS nx_identities (
    workspace   uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    uid         text NOT NULL,              -- the resource's identity_id
    first_seen  bigint NOT NULL,
    last_seen   bigint NOT NULL,
    sessions    int NOT NULL DEFAULT 1,
    last_name   text NOT NULL DEFAULT '',
    banned      boolean NOT NULL DEFAULT false,
    ban_reason  text,
    banned_at   bigint,
    last_server uuid REFERENCES nx_servers(id) ON DELETE SET NULL,
    PRIMARY KEY (workspace, uid)
);

CREATE INDEX IF NOT EXISTS nx_identities_seen ON nx_identities(workspace, last_seen DESC);
CREATE INDEX IF NOT EXISTS nx_identities_name ON nx_identities(workspace, lower(last_name));
CREATE INDEX IF NOT EXISTS nx_identities_banned ON nx_identities(workspace, banned) WHERE banned;

CREATE TABLE IF NOT EXISTS nx_identity_marks (
    workspace   uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    uid         text NOT NULL,
    kind        text NOT NULL,              -- license2 license discord fivem steam ip token device name
    value       text NOT NULL,
    first_seen  bigint NOT NULL,
    last_seen   bigint NOT NULL,
    times_seen  int NOT NULL DEFAULT 1,
    PRIMARY KEY (workspace, uid, kind, value)
);

-- The link lookup. Everything the alias search does is "who else carries this
-- (kind, value)", so this index is what makes the traversal a series of index
-- probes instead of a repeated table scan.
CREATE INDEX IF NOT EXISTS nx_identity_marks_lookup
    ON nx_identity_marks(workspace, kind, value);

CREATE INDEX IF NOT EXISTS nx_identity_marks_uid
    ON nx_identity_marks(workspace, uid);

-- Where the mirror has got to for each server, so a resync resumes instead of
-- replaying every identity the server has ever seen.
ALTER TABLE nx_servers ADD COLUMN IF NOT EXISTS identity_cursor bigint NOT NULL DEFAULT 0;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['nx_identities','nx_identity_marks']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON TABLE %I FROM anon, authenticated', t);
    END LOOP;
END $$;
