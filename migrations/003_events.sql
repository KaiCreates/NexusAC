-- The raw event log behind the Events page.
--
-- High volume by design: this is every spawn, shot, explosion and connection the
-- resource chose to record, not the curated staff log in nx_audit. The resource
-- samples the noisy types before they ever leave the game server (see
-- server/sv_events.lua); what lands here is already the part worth keeping.
--
-- Idempotent ingestion. Each resource session has a boot id and a sequence that
-- increases within it, so (server, boot, seq) identifies a row exactly once. A
-- retried or duplicated sync inserts nothing rather than double-logging.

CREATE TABLE IF NOT EXISTS nx_events (
    id          bigserial PRIMARY KEY,
    workspace   uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    server      uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    boot        text NOT NULL,
    seq         bigint NOT NULL,
    at          bigint NOT NULL,
    type        text NOT NULL,
    sender      text,
    sender_name text,
    target      text,
    target_name text,
    data        jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (server, boot, seq)
);

-- The page's default view: newest first for a workspace. id breaks ties so
-- keyset pagination is stable when many events share a second.
CREATE INDEX IF NOT EXISTS nx_events_recent ON nx_events(workspace, at DESC, id DESC);

-- Filtering by type is the single most common narrowing, and by sender the
-- second.
CREATE INDEX IF NOT EXISTS nx_events_type   ON nx_events(workspace, type, at DESC);
CREATE INDEX IF NOT EXISTS nx_events_sender ON nx_events(workspace, sender);
CREATE INDEX IF NOT EXISTS nx_events_names  ON nx_events(workspace, lower(sender_name));

-- data.* field queries (event_type:x && data.weaponType:y) are containment
-- checks, which is exactly what jsonb_path_ops is for and it is roughly half
-- the size of the default opclass.
CREATE INDEX IF NOT EXISTS nx_events_data   ON nx_events USING gin(data jsonb_path_ops);

-- Where each server's event mirror has got to. The boot is stored alongside the
-- sequence because the sequence restarts at zero on every resource start, so a
-- lower sequence under a NEW boot is a fresh session, not a replay.
ALTER TABLE nx_servers ADD COLUMN IF NOT EXISTS event_boot   text;
ALTER TABLE nx_servers ADD COLUMN IF NOT EXISTS event_cursor bigint NOT NULL DEFAULT 0;

DO $$
BEGIN
    EXECUTE 'ALTER TABLE nx_events ENABLE ROW LEVEL SECURITY';
    EXECUTE 'REVOKE ALL ON TABLE nx_events FROM anon, authenticated';
END $$;
