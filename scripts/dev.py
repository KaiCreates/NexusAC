"""Run the website locally on http://localhost:3000."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
