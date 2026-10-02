-- Short-lived live-view state. Frames are a replace-in-place cache, never
-- evidence; a viewer lease expires quickly if their browser stops polling.
CREATE TABLE IF NOT EXISTS nx_stream_viewers (
    server         uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    viewer         uuid NOT NULL,
    actor          uuid NOT NULL REFERENCES nx_users(id) ON DELETE CASCADE,
    target         int NOT NULL CHECK (target BETWEEN 1 AND 1024),
    player_session text NOT NULL,
    capture_session text,
    expires        bigint NOT NULL,
    PRIMARY KEY (server, viewer)
);
CREATE INDEX IF NOT EXISTS nx_stream_viewers_active
    ON nx_stream_viewers(server, target, expires);

CREATE TABLE IF NOT EXISTS nx_stream_frames (
    server          uuid NOT NULL REFERENCES nx_servers(id) ON DELETE CASCADE,
    target          int NOT NULL CHECK (target BETWEEN 1 AND 1024),
    capture_session text NOT NULL,
    frame_seq       bigint NOT NULL CHECK (frame_seq > 0),
    data            text NOT NULL,
    updated         bigint NOT NULL,
    PRIMARY KEY (server, target)
);
CREATE INDEX IF NOT EXISTS nx_stream_frames_expiry ON nx_stream_frames(updated);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['nx_stream_viewers','nx_stream_frames']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON TABLE %I FROM anon, authenticated', t); END IF;
    END LOOP;
END $$;
