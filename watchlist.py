"""
Watch list manager for HGC portal.
Tracks games that were "Not Found" in a saved run, and auto-resolves them
when a matching certification appears in the DB after a scrape + ingest.
"""

import json
from datetime import datetime
from pathlib import Path

from matcher import match_games

WATCHLIST_PATH = Path(__file__).parent / "watchlist.json"


def _load() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return json.loads(WATCHLIST_PATH.read_text())
    except Exception:
        return []


def _save(entries: list[dict]):
    WATCHLIST_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2))


def add_to_watchlist(
    game_name: str,
    provider: str,
    run_file: str,
    run_name: str,
    threshold: int,
):
    """Add a game to the watch list if not already present."""
    entries = _load()
    for e in entries:
        if e["game_name"] == game_name and e["run_file"] == run_file:
            return  # already watching
    entries.append(
        {
            "game_name": game_name,
            "provider": provider,
            "run_file": run_file,
            "run_name": run_name,
            "threshold": threshold,
            "added_at": datetime.now().isoformat(),
        }
    )
    _save(entries)


def remove_from_watchlist(game_name: str, run_file: str):
    """Remove a resolved entry from the watch list."""
    entries = _load()
    entries = [
        e for e in entries
        if not (e["game_name"] == game_name and e["run_file"] == run_file)
    ]
    _save(entries)


def get_watchlist() -> list[dict]:
    """Return current watch list entries."""
    return _load()


def check_watchlist(db_path) -> list[dict]:
    """
    Run the matcher against all watch list entries.
    For any entry where a match >= threshold is found:
      - Update the saved run JSON's `resolved` dict with source "Watch list match"
      - Remove the entry from the watch list
    Returns a list of resolved items for reporting.
    """
    from pathlib import Path as _Path

    entries = _load()
    if not entries:
        return []

    resolved_items = []

    # Group by run_file so we only load/save each run file once
    by_run: dict[str, list[dict]] = {}
    for e in entries:
        by_run.setdefault(e["run_file"], []).append(e)

    for run_file, run_entries in by_run.items():
        run_path = _Path(run_file)
        if not run_path.exists():
            # Run file was deleted — remove orphaned watchlist entries
            for e in run_entries:
                remove_from_watchlist(e["game_name"], run_file)
            continue

        try:
            run_data = json.loads(run_path.read_text())
        except Exception:
            continue

        run_resolved = run_data.setdefault("resolved", {})
        changed = False

        for e in run_entries:
            # Skip if already resolved some other way
            if e["game_name"] in run_resolved:
                remove_from_watchlist(e["game_name"], run_file)
                continue

            # Run matcher for this single game
            matches = match_games(
                [(e["game_name"], e["provider"])],
                db_path=_Path(db_path),
                limit=1,
            )
            if not matches:
                continue

            m = matches[0]
            if not m["review"] and m["confidence"] >= e["threshold"]:
                run_resolved[e["game_name"]] = {
                    "provider":      e["provider"],
                    "hgc_code":      m["hgc_code"],
                    "matched_title": m["matched_title"],
                    "manufacturer":  m["manufacturer"],
                    "operator":      m.get("operator", ""),
                    "source":        "Watch list match",
                }
                changed = True
                resolved_items.append(
                    {
                        "game_name":     e["game_name"],
                        "run_name":      e["run_name"],
                        "hgc_code":      m["hgc_code"],
                        "matched_title": m["matched_title"],
                        "confidence":    m["confidence"],
                    }
                )
                remove_from_watchlist(e["game_name"], run_file)

        if changed:
            run_path.write_text(json.dumps(run_data, ensure_ascii=False, indent=2))

    return resolved_items
