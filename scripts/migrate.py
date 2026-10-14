"""Kept so an older Render start command (`python scripts/migrate.py && uvicorn ...`)
still works. The new site creates its one table itself at startup; nothing to do."""
print("NexusAC web panel: no migrations needed (state table is created at startup).")
