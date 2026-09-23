-- The punishment record: every ban, kick, warning and reversal.
--
-- Kept apart from nx_events on purpose. An event is high volume, sampled, and
-- swept after 30 days. A punishment is low volume, never sampled, and is the
-- thing somebody appeals against a year later -- so there is no retention sweep
-- on this table at all.
--
-- It is also shaped differently: an event has a free-form payload, a punishment
-- has an actor, a reason, a duration and an evidence case, and those need to be
-- columns you can filter and sort on rather than keys inside a jsonb blob.

CREATE TABLE IF NOT EXISTS nx_punishments (
    id         bigserial PRIMARY KEY,
    workspace  uuid NOT NULL REFERENCES nx_workspaces(id) ON DELETE CASCADE,
    server     uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    boot       text NOT NULL,
    seq        bigint NOT NULL,
    at         bigint NOT NULL,
    kind       text NOT NULL,          -- ban | kick | warn | unban | unwarn
    identifier text,                   -- ties the row to the Identities page
    name       text,
    reason     text,
    by_actor   text,                   -- the staff member, or NexusAC
    auto       boolean NOT NULL DEFAULT false,
    days       int,                    -- ban length; 0 = permanent, null = n/a
    detector   text,
    evidence   text,
    UNIQUE (server, boot, seq)
);

CREATE INDEX IF NOT EXISTS nx_punishments_recent
    ON nx_punishments(workspace, at DESC, id DESC);
CREATE INDEX IF NOT EXISTS nx_punishments_kind
    ON nx_punishments(workspace, kind, at DESC);
-- "Everything this account has ever collected" is the whole point of the page.
CREATE INDEX IF NOT EXISTS nx_punishments_identifier
    ON nx_punishments(workspace, identifier, at DESC);
CREATE INDEX IF NOT EXISTS nx_punishments_actor
    ON nx_punishments(workspace, lower(by_actor));
CREATE INDEX IF NOT EXISTS nx_punishments_name
    ON nx_punishments(workspace, lower(name));

ALTER TABLE nx_servers ADD COLUMN IF NOT EXISTS punish_boot   text;
ALTER TABLE nx_servers ADD COLUMN IF NOT EXISTS punish_cursor bigint NOT NULL DEFAULT 0;

DO $$
BEGIN
    EXECUTE 'ALTER TABLE nx_punishments ENABLE ROW LEVEL SECURITY';
    EXECUTE 'REVOKE ALL ON TABLE nx_punishments FROM anon, authenticated';
END $$;
