#!/usr/bin/env python3
"""
apple_news_to_reader_poc.py  — PROOF OF CONCEPT (with resume/dedupe)

Import your Apple News "Saved Stories" into Readwise Reader, a few at a time.

What it does
------------
1. Reads the Apple News saved-stories file on this Mac.
2. Skips anything it has already imported (tracked in a local ledger file that
   lives NEXT TO this script: apple_news_imported.txt).
3. Takes up to LIMIT of the remaining/new stories.
4. Saves each to Readwise Reader via the official Readwise CLI, by handing Reader
   the `apple.news/<id>` link and letting Reader resolve it.
5. Records each successful import in the ledger, so re-runs never duplicate and
   simply pick up where you left off.

Because it hands Reader the apple.news link, this stays dependency-free (Python
standard library only). If some links don't resolve well inside Reader, set
RESOLVE = True to resolve to the publisher URL first (still stdlib-only).

Note: this does NOT (and cannot reliably) "un-save" articles in Apple News —
Apple offers no API for that and the local file is just a cache of an iCloud
list. The ledger is what prevents re-importing, so un-saving isn't needed.

Prerequisites (one time)
------------------------
  npm install -g @readwise/cli          # needs Node.js/npm
  readwise login                        # or: readwise login-with-token <token>
  # ...and open the News app once on this Mac with iCloud News sync on.

Run
---
  python3 apple_news_to_reader_poc.py   # imports up to LIMIT new stories
  # Preview only (saves nothing, writes nothing to the ledger): set DRY_RUN = True

Extraction technique adapted from RhetTbull / Dave Bullock (eecue):
  https://gist.github.com/RhetTbull/06617e33fe8645f75260311ab582fb6d
"""

from __future__ import annotations

import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ----------------------------- settings -----------------------------
LIMIT = 10000        # how many NEW saved stories to import this run
DRY_RUN = False      # True = show what would happen, save nothing, touch nothing
RESOLVE = False      # True = resolve apple.news -> publisher URL before saving
TAG = ""             # tag applied to imported docs ("" to skip tagging)
SLEEP_SECONDS = 2    # pause between saves (be gentle with the rate limiter)
# --------------------------------------------------------------------

# The dedupe ledger lives alongside this script.
try:
    SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
except NameError:  # e.g. run via stdin
    SCRIPT_DIR = pathlib.Path.cwd()
LEDGER = SCRIPT_DIR / "apple_news_imported.txt"

READING_LIST = (
    pathlib.Path.home()
    / "Library/Containers/com.apple.news/Data/Library/Application Support"
    / "com.apple.news/com.apple.news.public-com.apple.news.private-production"
    / "reading-list"
)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


def load_ledger() -> set[str]:
    """IDs already imported in previous runs."""
    if LEDGER.exists():
        return {
            ln.strip()
            for ln in LEDGER.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }
    return set()


def record_imported(news_id: str) -> None:
    """Append one imported ID to the ledger (written immediately, so an
    interrupted run is still safely resumable)."""
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(news_id + "\n")


def find_article_ids() -> list[str]:
    """Return the saved Apple News article IDs, newest first.

    The `reading-list` file embeds several binary plists; the second one holds
    the saved-articles data. We parse it and collect every 'articleID' we find.
    """
    if not READING_LIST.exists():
        sys.exit(
            "Could not find the Apple News saved-stories file:\n"
            f"  {READING_LIST}\n\n"
            "Fix: open the News app once on this Mac with iCloud sync for News on."
        )

    data = READING_LIST.read_bytes()
    markers = [m.start() for m in re.finditer(re.escape(b"bplist00"), data)]
    if len(markers) < 2:
        sys.exit("Couldn't locate the saved-articles plist inside 'reading-list'.")
    start = markers[1]
    end = markers[2] if len(markers) > 2 else len(data)

    try:
        parsed = plistlib.loads(data[start:end], fmt=plistlib.FMT_BINARY)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Failed to parse the saved-articles plist: {e}")

    ids: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            val = obj.get("articleID")
            if isinstance(val, str):
                ids.append(val)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)

    walk(parsed)

    seen, unique = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    return unique


def resolve_publisher_url(news_id: str) -> str | None:
    """Optionally resolve apple.news/<id> to the real publisher URL."""
    url = f"https://apple.news/{news_id}"
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return None
    m = re.search(r'redirectToUrlAfterTimeout.*?"(https://[^"]+)"', html, re.S)
    if m and "apple.news" not in m.group(1):
        return m.group(1)
    m = re.search(r'<link[^>]+rel="canonical"[^>]+href="(https://[^"]+)"', html)
    if m and "apple.news" not in m.group(1):
        return m.group(1)
    return None


def save_to_reader(url: str) -> tuple[bool, str]:
    """Save a URL to Reader with the readwise CLI."""
    cmd = ["readwise", "reader-create-document", "--url", url]
    if TAG:
        cmd += ["--tags", TAG]  # if your CLI version rejects --tags, remove this
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except FileNotFoundError:
        sys.exit("`readwise` CLI not found. Install: npm install -g @readwise/cli")
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def main() -> None:
    if not DRY_RUN and shutil.which("readwise") is None:
        sys.exit(
            "`readwise` CLI not found on PATH.\n"
            "Install & log in:\n"
            "  npm install -g @readwise/cli\n"
            "  readwise login"
        )

    already = load_ledger()
    all_ids = find_article_ids()
    pending = [i for i in all_ids if i not in already]

    print(f"Saved stories in Apple News : {len(all_ids)}")
    print(f"Already imported (ledger)   : {len(already)}")
    print(f"New / not yet imported      : {len(pending)}")
    print(f"Ledger file                 : {LEDGER}")
    print(f"Importing up to {LIMIT} this run"
          + (" — DRY RUN (nothing saved or recorded)\n" if DRY_RUN else "\n"))

    imported = skipped = 0
    for n, news_id in enumerate(pending[:LIMIT], start=1):
        target = f"https://apple.news/{news_id}"
        if RESOLVE:
            pub = resolve_publisher_url(news_id)
            if not pub:
                print(f"[{n}] SKIP  {news_id} — couldn't resolve a public URL "
                      "(News+ exclusive or blocked).")
                skipped += 1
                continue
            target = pub

        print(f"[{n}] {target}")
        if DRY_RUN:
            imported += 1
            continue

        ok, msg = save_to_reader(target)
        if ok:
            record_imported(news_id)          # mark done immediately
            print("      saved ✓")
            imported += 1
        else:
            print(f"      FAILED — {msg}")
            skipped += 1
        time.sleep(SLEEP_SECONDS)

    print(f"\nDone. {imported} imported, {skipped} skipped this run.")
    remaining = len(pending) - imported if not DRY_RUN else len(pending)
    if remaining > 0:
        print(f"{remaining} still to go — re-run to continue "
              "(or raise LIMIT to do more per run).")
    if not DRY_RUN and imported and TAG:
        print(f"Check your Reader inbox (location: New), filtered by '{TAG}'.")


if __name__ == "__main__":
    main()
