"""
Fuzzy-match (game_name, provider) pairs against the certifications DB.
Provider is matched against manufacturer to narrow candidates before
matching the game title.
"""

import json
import sqlite3
from pathlib import Path
from rapidfuzz import process, fuzz

DB_PATH           = Path(__file__).parent / "hgc.db"
PROVIDER_MAP_PATH = Path(__file__).parent / "provider_map.json"
CONFIDENCE_THRESHOLD = 88  # below this → Not Found (single shared words score ~85)
PROVIDER_THRESHOLD = 70   # min score to trust a provider match


def load_provider_map() -> dict:
    """Read the learned provider→manufacturer map. Returns {} if missing."""
    try:
        return json.loads(PROVIDER_MAP_PATH.read_text())
    except Exception:
        return {}


def save_provider_map(provider_map: dict):
    """Write the provider→manufacturer map to disk."""
    PROVIDER_MAP_PATH.write_text(json.dumps(provider_map, ensure_ascii=False, indent=2))


def _load_db(db_path: Path):
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT hgc_code, title, trade_name, manufacturer, operator FROM certifications"
    ).fetchall()
    con.close()
    return rows


def _score(a: str, b: str, **kwargs) -> float:
    """
    Blend ratio (full string similarity) and token_sort_ratio (order-insensitive).
    This prevents a single shared token like "Wild" or "Fortune" from inflating scores.
    """
    return 0.6 * fuzz.ratio(a, b) + 0.4 * fuzz.token_sort_ratio(a, b)


def _best_title_match(game_name: str, candidates: list, limit: int = 3):
    """Return top fuzzy title matches from a candidate list."""
    choices = {r[1]: r for r in candidates}  # title → row
    choices.update({r[2]: r for r in candidates if r[2]})  # trade_name → row
    hits = process.extract(game_name, list(choices.keys()), scorer=_score, limit=limit)
    return [(choices[m], s) for m, s, _ in hits]


def match_games(pairs: list[tuple[str, str]], db_path: Path = DB_PATH, limit: int = 6) -> list[dict]:
    """
    pairs: list of (game_name, provider) tuples.
    Returns list of match dicts.
    """
    all_rows = _load_db(db_path)

    # Build manufacturer index for provider matching
    manufacturers = list({r[3] for r in all_rows if r[3]})

    provider_map = load_provider_map()

    results = []
    for game_name, provider in pairs:
        # Step 1: find best manufacturer match for the given provider
        # Check the learned map first (case-insensitive key lookup)
        provider_lower = provider.strip().lower()
        map_key = next((k for k in provider_map if k.lower() == provider_lower), None)
        if map_key:
            matched_mfr = provider_map[map_key]
            fuzzy_resolved = False
        else:
            mfr_hits = process.extract(provider, manufacturers, scorer=fuzz.WRatio, limit=1) if provider.strip() else []
            matched_mfr = mfr_hits[0][0] if mfr_hits and mfr_hits[0][1] >= PROVIDER_THRESHOLD else None
            fuzzy_resolved = matched_mfr is not None
            # Save new fuzzy-resolved provider→manufacturer pairs to the map
            if fuzzy_resolved and provider.strip():
                provider_map[provider.strip()] = matched_mfr
                save_provider_map(provider_map)

        # Step 2: try within matched manufacturer first
        if matched_mfr:
            scoped = [r for r in all_rows if r[3] == matched_mfr]
            hits = _best_title_match(game_name, scoped, limit)
        else:
            hits = []

        # Step 3: fall back to global if no good scoped match
        if not hits or hits[0][1] < CONFIDENCE_THRESHOLD:
            global_hits = _best_title_match(game_name, all_rows, limit)
            if not hits or (global_hits and global_hits[0][1] > hits[0][1]):
                hits = global_hits

        if not hits:
            results.append({
                "game_name": game_name,
                "provider": provider,
                "hgc_code": None,
                "matched_title": None,
                "manufacturer": None,
                "operator": None,
                "confidence": 0,
                "review": True,
                "alternatives": [],
            })
            continue

        best_row, best_score = hits[0]
        hgc, title, trade, mfr, operator = best_row
        results.append({
            "game_name": game_name,
            "provider": provider,
            "hgc_code": hgc,
            "matched_title": title,
            "manufacturer": mfr,
            "operator": operator,
            "confidence": round(best_score, 1),
            "review": best_score < CONFIDENCE_THRESHOLD,
            "alternatives": [
                {
                    "matched_title": r[1],
                    "hgc_code": r[0],
                    "manufacturer": r[3],
                    "confidence": round(s, 1),
                }
                for r, s in hits[1:]
            ],
        })

    return results
