"""Copy the in-game panel (NexusAC/html) into the website.

    python scripts/sync_panel.py "<path to>/NexusAC"

Run it after every change to the in-game panel, then deploy. The files are
copied as they are, with one exception: the NUI DevTools watch at the end of
panel.js is removed -- on a website it would pause anyone who opens their
browser's developer tools, and it reports to the game, which is not there.
"""
import re
import shutil
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "app" / "panel"
FILES = ("panel.html", "panel.css", "panel.js", "clip.js")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]) / "html"
    if not (src / "panel.js").is_file():
        sys.exit(f"No panel.js in {src}")
    DEST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(src / name, DEST / name)

    js = (DEST / "panel.js").read_text(encoding="utf-8")
    start = js.find("/* Anti NUI DevTools")
    if start == -1:
        sys.exit("panel.js changed: could not find the DevTools watch to remove. Check sync_panel.py.")
    end = js.find("})();", start)
    js = js[:start] + "/* (DevTools watch removed for the website by scripts/sync_panel.py) */\n" + js[end + len("})();"):]
    if re.search(r"\bdebugger\s*;", js):
        sys.exit("panel.js still contains a debugger statement.")
    (DEST / "panel.js").write_text(js, encoding="utf-8", newline="\n")
    print("Copied", ", ".join(FILES), "->", DEST)


if __name__ == "__main__":
    main()
