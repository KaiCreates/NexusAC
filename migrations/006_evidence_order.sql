-- Keep the newest cases at the top even when older cases are updated by sync.
CREATE INDEX IF NOT EXISTS nx_evidence_case_at
ON nx_evidence (server, ((body->>'at')::double precision) DESC, id DESC);
