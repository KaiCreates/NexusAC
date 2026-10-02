-- On-demand inventory lookups. A staff member queues an `inventory` command;
-- the game server answers through /bridge/inventory and the page polls for it.
-- Short-lived cache (pruned after 10 minutes), never a mirror of inventories.
CREATE TABLE IF NOT EXISTS nx_inventory_views (
    server     uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    command_id uuid NOT NULL,
    operation  text NOT NULL,
    ok         boolean NOT NULL DEFAULT true,
    message    text NOT NULL DEFAULT '',
    body       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created    bigint NOT NULL,
    PRIMARY KEY (server, command_id)
);
CREATE INDEX IF NOT EXISTS nx_inventory_views_expiry ON nx_inventory_views(created);

ALTER TABLE nx_inventory_views ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE nx_inventory_views FROM anon, authenticated;
