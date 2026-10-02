-- The website signs people in itself (app/local_auth.py) instead of through
-- Supabase Auth, so it can run on any Postgres (Neon, Render, self-hosted).
-- Accounts copied from the Supabase era have no password_hash until one is set
-- with scripts/set_password.py; they cannot sign in before that.
ALTER TABLE nx_users ADD COLUMN IF NOT EXISTS password_hash text;
CREATE UNIQUE INDEX IF NOT EXISTS nx_users_email_lower ON nx_users(lower(email));

-- Retention (app/maintenance.py) deletes by age; these keep it from scanning.
CREATE INDEX IF NOT EXISTS nx_media_created ON nx_media(created);
CREATE INDEX IF NOT EXISTS nx_evidence_age ON nx_evidence(updated);
CREATE INDEX IF NOT EXISTS nx_commands_created ON nx_commands(created);
CREATE INDEX IF NOT EXISTS nx_audit_at ON nx_audit(at);
CREATE INDEX IF NOT EXISTS nx_limits_expires ON nx_limits(expires);
CREATE INDEX IF NOT EXISTS nx_bridge_boots_at ON nx_bridge_boots(at);
