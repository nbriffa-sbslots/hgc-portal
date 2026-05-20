import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from matcher import match_games, load_provider_map, save_provider_map
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
from watchlist import add_to_watchlist, get_watchlist, remove_from_watchlist
from rapidfuzz import process, fuzz

KNOWN_PROVIDERS = [
    "Amusnet", "Big Time Gaming", "Egt Digital", "Endorphina via Bragg",
    "Evolution", "Games Global", "Greentube", "Hacksaw via Relax", "IGT",
    "Inspired via Relax", "Netent", "Nolimit City", "Oryx (Bragg)",
    "Play 'N Go", "Playson via Bragg", "Playtech", "Push Gaming",
    "Pragmatic Play", "RedTiger", "Relax Gaming", "Spribe via Bragg",
    "Superbet", "Synot", "Wazdan",
]
PROVIDER_NORM_THRESHOLD = 75


def normalize_provider(raw: str) -> tuple[str, bool]:
    """Return (canonical_name, flagged).
    flagged=True means no confident match was found."""
    if not raw:
        return raw, False
    # Exact match first (case-insensitive)
    for p in KNOWN_PROVIDERS:
        if p.lower() == raw.lower():
            return p, False
    # Fuzzy match
    hits = process.extract(raw, KNOWN_PROVIDERS, scorer=fuzz.WRatio, limit=1)
    if hits and hits[0][1] >= PROVIDER_NORM_THRESHOLD:
        return hits[0][0], False
    return raw, True  # flagged — no confident match

st.set_page_config(page_title="HGC Certification Lookup", page_icon="🏛️", layout="wide")

# ── Greece-themed CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0a1628; color: #e8edf5; }
  [data-testid="stHeader"] { background: transparent; }

  [data-testid="stSidebar"] { background: #0d1f3c; border-right: 1px solid #1a3a6e; }
  [data-testid="stSidebar"] * { color: #c8d8f0 !important; }

  .hero {
      background: linear-gradient(135deg, #0d3880 0%, #1a5fc8 60%, #2979d4 100%);
      border-radius: 12px; padding: 28px 36px; margin-bottom: 24px;
      border-left: 6px solid #ffffff;
  }
  .hero h1 { margin: 0; font-size: 2rem; color: #ffffff; font-weight: 800; letter-spacing: -0.5px; }
  .hero p  { margin: 4px 0 0; color: #a8c8f0; font-size: 0.95rem; }

  [data-testid="metric-container"] {
      background: #0d1f3c; border: 1px solid #1a3a6e; border-radius: 10px; padding: 16px;
  }
  [data-testid="stMetricLabel"] { color: #7a9cc8 !important; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
  [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 2rem !important; }

  [data-testid="stTabs"] button { color: #7a9cc8 !important; font-weight: 600; font-size: 0.9rem; }
  [data-testid="stTabs"] button[aria-selected="true"] { color: #ffffff !important; border-bottom: 2px solid #4a9fea !important; }
  [data-testid="stTabsContent"] { background: #0d1f3c; border: 1px solid #1a3a6e; border-radius: 0 10px 10px 10px; padding: 20px; }

  textarea, [data-testid="stTextArea"] textarea {
      background: #0d1f3c !important; color: #e8edf5 !important;
      border: 1px solid #1a3a6e !important; border-radius: 8px !important;
  }
  textarea:focus { border-color: #4a9fea !important; }

  [data-testid="stButton"] button[kind="primary"] {
      background: linear-gradient(135deg, #1a5fc8, #2979d4) !important;
      color: #ffffff !important; border: none !important;
      border-radius: 8px !important; font-weight: 700 !important; padding: 10px 28px !important;
  }
  [data-testid="stButton"] button[kind="secondary"] {
      background: transparent !important; color: #4a9fea !important;
      border: 1px solid #4a9fea !important; border-radius: 8px !important;
  }
  [data-testid="stDownloadButton"] button {
      background: #0d3880 !important; color: #ffffff !important;
      border: 1px solid #4a9fea !important; border-radius: 8px !important; font-weight: 600 !important;
  }
  [data-testid="stExpander"] {
      background: #0a1628 !important; border: 1px solid #1a3a6e !important; border-radius: 8px !important; margin-bottom: 8px;
  }
  [data-testid="stExpander"] summary { color: #c8d8f0 !important; font-weight: 600; }

  .run-card {
      background: #0d1f3c; border: 1px solid #1a3a6e; border-radius: 10px;
      padding: 14px 18px; margin-bottom: 4px;
  }
  .run-card:hover { border-color: #4a9fea; }
  .run-card .run-name { font-weight: 700; color: #ffffff; font-size: 0.95rem; }
  .run-card .run-meta { color: #7a9cc8; font-size: 0.75rem; margin-top: 3px; }
  .run-card-active {
      background: #112244 !important; border: 1px solid #1a3a6e !important;
      border-left: 3px solid #4a9fea !important; border-radius: 10px;
      padding: 14px 18px; margin-bottom: 4px;
  }
  .run-card-active:hover { border-color: #4a9fea; }
  .run-card-active .run-name { font-weight: 700; color: #ffffff; font-size: 0.95rem; }
  .run-card-active .run-meta { color: #7a9cc8; font-size: 0.75rem; margin-top: 3px; }
  .active-tag {
      color: #4a9fea; font-size: 0.75rem; font-weight: 700; margin-top: 4px;
  }

  /* Sidebar run action buttons */
  [data-testid="stSidebar"] [data-testid="stButton"] button {
      background: #0a1628 !important;
      border: 1px solid #1a3a6e !important;
      color: #a8c0e0 !important;
      border-radius: 6px !important;
      font-size: 0.78rem !important;
      padding: 4px 0 !important;
      width: 100%;
      transition: border-color 0.15s, color 0.15s;
  }
  [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
      border-color: #4a9fea !important;
      color: #ffffff !important;
  }

  hr { border-color: #1a3a6e !important; }
  [data-testid="stRadio"] label { color: #c8d8f0 !important; }
  h2, h3 { color: #c8d8f0 !important; }
  p, label, .stMarkdown { color: #a8c0e0; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
DB_PATH        = Path(__file__).parent / "hgc.db"
NEW_CERTS_PATH = Path(__file__).parent / "new_certs.json"

if not DB_PATH.exists():
    st.error("Database not found. Run `python ingest.py` first.")
    st.stop()

# Ensure runs table exists
def _ensure_runs_table():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            name      TEXT PRIMARY KEY,
            saved_at  TEXT,
            threshold INTEGER,
            results   TEXT,
            resolved  TEXT
        )
    """)
    con.commit()
    con.close()

_ensure_runs_table()

# ── Run persistence helpers ────────────────────────────────────────────────────
def save_run(name: str, results: list, resolved: dict, threshold: int):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT OR REPLACE INTO runs (name, saved_at, threshold, results, resolved) VALUES (?,?,?,?,?)",
        (name, datetime.now().isoformat(), threshold,
         json.dumps(results, ensure_ascii=False),
         json.dumps(resolved, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def load_runs() -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT name, saved_at, threshold, results, resolved FROM runs ORDER BY saved_at DESC"
    ).fetchall()
    con.close()
    return [
        {
            "name":      r[0],
            "saved_at":  r[1],
            "threshold": r[2],
            "results":   json.loads(r[3]),
            "resolved":  json.loads(r[4]),
        }
        for r in rows
    ]


def delete_run(run_name: str):
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM runs WHERE name = ?", (run_name,))
    con.commit()
    con.close()


def run_status(run: dict) -> tuple[str, str]:
    threshold  = run.get("threshold", 88)
    results    = run.get("results", [])
    resolved   = run.get("resolved", {})
    not_found  = [r for r in results if r.get("review") or r.get("confidence", 0) < threshold]
    still_open = [r for r in not_found if r["game_name"] not in resolved]
    if still_open:
        return f"{len(still_open)} open", "open"
    elif resolved:
        return "All resolved", "resolved"
    else:
        return "Complete", "done"


# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div>
    <h1>🏛️ HGC Certification Lookup</h1>
    <p>Hellenic Gaming Commission &nbsp;·&nbsp; Certified game registry &nbsp;·&nbsp; Greece</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: saved runs ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📂 Saved Runs")
    all_runs = load_runs()

    if not all_runs:
        st.caption("No saved runs yet.")
    else:
        for run in all_runs:
            status_label, status_type = run_status(run)
            badge_colour = {"open": "#c0392b", "resolved": "#1a5fc8", "done": "#1e7e34"}[status_type]
            saved_dt = datetime.fromisoformat(run["saved_at"]).strftime("%d %b %Y · %H:%M")
            total    = len(run.get("results", []))
            resolved_count = len(run.get("resolved", {}))
            is_active = st.session_state.get("run_name") == run["name"]
            card_class = "run-card-active" if is_active else "run-card"
            active_tag = "<div class='active-tag'>&#9654; Active</div>" if is_active else ""

            st.markdown(f"""
            <div class="{card_class}">
              <div class="run-name">{run['name']}</div>
              <div class="run-meta">{saved_dt}</div>
              <div class="run-meta" style="margin-top:2px">{total} games &nbsp;·&nbsp; {resolved_count} resolved</div>
              <div style="margin-top:8px">
                <span style="background:{badge_colour};color:#fff;border-radius:12px;
                             padding:2px 10px;font-size:0.72rem;font-weight:700;
                             letter-spacing:0.03em">{status_label.upper()}</span>
              </div>
              {active_tag}
            </div>
            """, unsafe_allow_html=True)

            run_key = run["name"].replace(" ", "_").replace("/", "-")
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if st.button("▶ Load", key=f"load_{run_key}", use_container_width=True):
                    prev_resolved_count = len(run.get("resolved", {}))
                    # Re-read from DB to pick up any watch-list auto-resolutions
                    fresh_runs = [r for r in load_runs() if r["name"] == run["name"]]
                    fresh = fresh_runs[0] if fresh_runs else run
                    new_resolved_count = len(fresh.get("resolved", {}))
                    wl_matches = new_resolved_count - prev_resolved_count
                    st.session_state["results"]    = fresh["results"]
                    st.session_state["threshold"]  = fresh["threshold"]
                    st.session_state["resolved"]   = fresh["resolved"]
                    st.session_state["run_name"]   = fresh["name"]
                    st.session_state["wl_matches"] = max(wl_matches, 0)
                    st.rerun()
            with btn_col2:
                rename_key = f"renaming_{run_key}"
                if st.button("✏️", key=f"ren_{run_key}", use_container_width=True,
                             help="Rename this run"):
                    st.session_state[rename_key] = not st.session_state.get(rename_key, False)
                    st.rerun()
            with btn_col3:
                if st.button("🗑", key=f"del_{run_key}", use_container_width=True,
                             help="Delete this run"):
                    delete_run(run["name"])
                    st.rerun()

            if st.session_state.get(f"renaming_{run_key}"):
                new_name = st.text_input(
                    "New name", value=run["name"],
                    key=f"rename_input_{run_key}",
                    label_visibility="collapsed",
                )
                if st.button("Save name", key=f"rename_save_{run_key}", use_container_width=True):
                    new_name = new_name.strip()
                    if new_name and new_name != run["name"]:
                        con = sqlite3.connect(DB_PATH)
                        con.execute("UPDATE runs SET name = ? WHERE name = ?", (new_name, run["name"]))
                        con.commit()
                        con.close()
                        if st.session_state.get("run_name") == run["name"]:
                            st.session_state["run_name"] = new_name
                    st.session_state[f"renaming_{run_key}"] = False
                    st.rerun()

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📊 Registry Stats")
    con = sqlite3.connect(DB_PATH)
    total_certs = con.execute("SELECT COUNT(*) FROM certifications").fetchone()[0]
    con.close()
    st.metric("Total certifications", f"{total_certs:,}")
    if NEW_CERTS_PATH.exists():
        try:
            last_scrape = json.loads(NEW_CERTS_PATH.read_text()).get("generated_at", "")
            last_scrape_dt = datetime.fromisoformat(last_scrape).strftime("%d %b %Y · %H:%M")
            st.caption(f"Last scraped: {last_scrape_dt}")
        except Exception:
            pass
    st.divider()
    with st.expander("🗂 Provider Map"):
        pm = load_provider_map()
        if not pm:
            st.caption("No learned mappings yet.")
        else:
            pm_df = pd.DataFrame(
                [{"Input Provider": k, "Mapped To": v} for k, v in pm.items()]
            )
            st.dataframe(pm_df, use_container_width=True, hide_index=True)
            st.caption("Delete an incorrect mapping:")
            for k in list(pm.keys()):
                if st.button(f"✕ {k}", key=f"del_pm_{k}"):
                    pm.pop(k)
                    save_provider_map(pm)
                    st.rerun()
    st.divider()
    st.markdown("**Scrape schedule**")
    st.markdown("🔄 Daily @ 09:00 CET")

# ── Top-level page tabs ────────────────────────────────────────────────────────
page_lookup, page_whats_new, page_nyr = st.tabs(["🔍 Certification Lookup", "🆕 What's New", "🚫 Not Yet In Registry"])

with page_whats_new:
    # ── Improvement 5: date-range selector querying DB directly ───────────────
    wn_range = st.radio(
        "Show certifications added in the last:",
        options=["7 days", "30 days", "90 days", "All time"],
        index=1,
        horizontal=True,
        key="wn_range",
    )

    cutoff_date = None
    if wn_range != "All time":
        days_map = {"7 days": 7, "30 days": 30, "90 days": 90}
        cutoff_date = datetime.now() - timedelta(days=days_map[wn_range])

    try:
        con = sqlite3.connect(DB_PATH)
        if cutoff_date is None:
            wn_rows = con.execute(
                "SELECT hgc_code, title, trade_name, manufacturer, operator, created "
                "FROM certifications ORDER BY created DESC"
            ).fetchall()
        else:
            # created is stored as DD/MM/YYYY HH:MM — fetch all and filter in Python
            # (SQLite text comparison on DD/MM/YYYY format is unreliable)
            wn_rows = con.execute(
                "SELECT hgc_code, title, trade_name, manufacturer, operator, created "
                "FROM certifications"
            ).fetchall()
        con.close()

        # Parse and filter by cutoff
        parsed_rows = []
        for row in wn_rows:
            hgc_code, title, trade_name, manufacturer, operator, created_str = row
            created_dt = None
            if created_str:
                try:
                    created_dt = datetime.strptime(created_str[:16], "%d/%m/%Y %H:%M")
                except Exception:
                    pass
            if cutoff_date is not None and (created_dt is None or created_dt < cutoff_date):
                continue
            parsed_rows.append({
                "HGC Code":      hgc_code,
                "Title":         title,
                "Manufacturer":  manufacturer,
                "Operator Use":  operator,
                "Created":       created_str or "",
                "_created_dt":   created_dt,
            })

        # Sort by created descending
        parsed_rows.sort(key=lambda x: x["_created_dt"] or datetime.min, reverse=True)

        st.markdown(
            f"<p style='color:#7a9cc8;font-size:0.9rem'>"
            f"<b style='color:#ffffff'>{len(parsed_rows)}</b> certifications"
            f" &nbsp;·&nbsp; range: <b style='color:#c8d8f0'>{wn_range}</b>"
            f"</p>",
            unsafe_allow_html=True,
        )

        if not parsed_rows:
            st.info("No certifications found for the selected period.")
        else:
            df_new = pd.DataFrame(parsed_rows).drop(columns=["_created_dt"])

            fc1, fc2 = st.columns(2)
            with fc1:
                mfr_opts   = ["All"] + sorted(df_new["Manufacturer"].dropna().unique().tolist())
                mfr_filter = st.selectbox("Filter by Manufacturer", mfr_opts, key="nc_mfr")
            with fc2:
                op_opts   = ["All"] + sorted(df_new["Operator Use"].dropna().unique().tolist())
                op_filter = st.selectbox("Filter by Operator Use", op_opts, key="nc_op")

            if mfr_filter != "All":
                df_new = df_new[df_new["Manufacturer"] == mfr_filter]
            if op_filter != "All":
                df_new = df_new[df_new["Operator Use"] == op_filter]

            st.dataframe(df_new, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download certifications",
                data=df_new.to_csv(index=False).encode("utf-8-sig"),
                file_name="new_certs.csv",
                mime="text/csv",
            )
    except Exception as e:
        st.error(f"Could not query database: {e}")

with page_lookup:
    st.subheader("New search")
    st.markdown(
        "Paste **two columns**: `Game Name` and `Provider`, separated by a tab or comma. "
        "One row per line. You can paste directly from Excel.",
    )

    col_input, col_opts = st.columns([3, 1])
    with col_input:
        st.caption("Paste directly from Excel — select your two columns and paste here.")
        if "game_input_v" not in st.session_state:
            st.session_state["game_input_v"] = 0
            initial_df = pd.DataFrame({"Game Name": [""] * 300, "Provider": [""] * 300})

        _empty = [""] * 300
        _none  = [None] * 300
        grid = st.data_editor(
            pd.DataFrame({
                "Game Name":     _empty,
                "Provider Name": _empty,
                "Product":       _none,
                "Game Category": _none,
            }),
            use_container_width=True,
            hide_index=True,
            height=320,
            key=f"game_input_{st.session_state['game_input_v']}",
            column_config={
                "Game Name":     st.column_config.TextColumn("Game Name",     width="large"),
                "Provider Name": st.column_config.TextColumn("Provider Name", width="medium"),
                "Product": st.column_config.SelectboxColumn(
                    "Product", width="medium",
                    options=["Casino", "Live Casino"],
                ),
                "Game Category": st.column_config.SelectboxColumn(
                    "Game Category", width="medium",
                    options=["Slot", "Table Game", "Baccarat", "Blackjack", "Roulette", "Crash", "Game Show"],
                ),
            },
        )
    with col_opts:
        st.markdown("**Options**")
        threshold = st.slider("Min confidence", 0, 100, 88)

    def _str(v):
        """Safely convert a cell value (may be NaN/None) to a clean string."""
        import math
        if v is None:
            return ""
        try:
            if math.isnan(float(v)):
                return ""
        except (TypeError, ValueError):
            pass
        return str(v).strip()

    pairs = [
        (_str(row["Game Name"]), _str(row["Provider Name"]))
        for _, row in grid.iterrows()
        if _str(row["Game Name"])
    ]
    extras = {
        _str(row["Game Name"]): {
            "product":       _str(row["Product"]),
            "game_category": _str(row["Game Category"]),
        }
        for _, row in grid.iterrows()
        if _str(row["Game Name"])
    }

    btn_col1, btn_col2 = st.columns([1, 5])
    with btn_col1:
        run_btn = st.button("Find HGC Codes", type="primary", disabled=not pairs)
    with btn_col2:
        if st.button("✕ Clear", disabled=not (pairs or "results" in st.session_state)):
            for key in ["results", "resolved", "run_name", "active_tab"]:
                st.session_state.pop(key, None)
            st.session_state["game_input_v"] = st.session_state.get("game_input_v", 0) + 1
            st.rerun()

    if run_btn and pairs:

        # ── Improvement 4: Duplicate detection across saved runs ──────────────
        saved_runs_for_dupe = load_runs()
        dupe_warnings = []
        for game_name, _provider in pairs:
            game_lower = game_name.lower()
            for sr in saved_runs_for_dupe:
                sr_game_names = [r["game_name"].lower() for r in sr.get("results", [])]
                if game_lower in sr_game_names:
                    dupe_warnings.append((game_name, sr["name"]))
                    break  # only report first matching run per game
        if dupe_warnings:
            dupe_list = ", ".join(
                f"**{g}** ({r})" for g, r in dupe_warnings
            )
            st.warning(f"⚠️ These games already appear in a saved run: {dupe_list}. Proceeding anyway.")

        try:
            with st.spinner(f"Matching {len(pairs)} games…"):
                results = match_games(pairs, limit=6)
        except Exception as e:
            st.error(f"Matching failed: {e}")
            st.stop()

        pm = load_provider_map()
        for r in results:
            if r.get("provider") and r.get("manufacturer") and not r.get("review"):
                pm.setdefault(r["provider"], r["manufacturer"])
        save_provider_map(pm)

        # Normalise provider names to canonical list; flag unknowns
        flagged_providers = []
        for ex_key in list(extras.keys()):
            raw = ex_key  # game_name is the key; provider is in the pairs
        # Build provider norm map from pairs
        provider_norm = {}
        for game_name, raw_provider in pairs:
            canonical, flagged = normalize_provider(raw_provider)
            provider_norm[game_name] = {"canonical": canonical, "flagged": flagged}
            if flagged and raw_provider:
                flagged_providers.append(raw_provider)

        st.session_state["results"]          = results
        st.session_state["threshold"]        = threshold
        st.session_state["resolved"]         = {}
        st.session_state["active_tab"]       = "matched"
        st.session_state["extras"]           = extras
        st.session_state["provider_norm"]    = provider_norm
        st.session_state["flagged_providers"] = list(dict.fromkeys(flagged_providers))
        st.session_state.pop("run_name", None)
        st.rerun()

    # ── Results ───────────────────────────────────────────────────────────────
    if "results" in st.session_state:
        results          = st.session_state["results"]
        threshold        = st.session_state.get("threshold", 88)
        resolved         = st.session_state.setdefault("resolved", {})
        extras           = st.session_state.get("extras", {})
        provider_norm    = st.session_state.get("provider_norm", {})
        flagged_providers = st.session_state.get("flagged_providers", [])

        if flagged_providers:
            st.warning("⚠️ Some providers couldn't be matched — please select the correct ones below:")
            fix_cols = st.columns(min(len(flagged_providers), 3))
            for i, raw_prov in enumerate(flagged_providers):
                with fix_cols[i % 3]:
                    choice = st.selectbox(
                        f'"{raw_prov}"',
                        options=["— keep as-is —"] + sorted(KNOWN_PROVIDERS),
                        key=f"prov_fix_{raw_prov}",
                    )
                    if choice != "— keep as-is —":
                        # Apply fix to all games that had this raw provider
                        for gn, norm in provider_norm.items():
                            if norm.get("canonical") == raw_prov:
                                provider_norm[gn] = {"canonical": choice, "flagged": False}
                        st.session_state["provider_norm"] = provider_norm
                        st.session_state["flagged_providers"] = [
                            p for p in flagged_providers if p != raw_prov
                        ]
                        st.rerun()

        wl_matches = st.session_state.pop("wl_matches", 0)
        if wl_matches:
            st.success(f"🎯 {wl_matches} game(s) matched from watch list and auto-resolved!")

        def is_found(r):
            return not r["review"] and r["confidence"] >= threshold

        found_results     = [r for r in results if is_found(r)]
        not_found_results = [r for r in results if not is_found(r)]
        still_open        = [r for r in not_found_results if r["game_name"] not in resolved]

        # ── Save run bar ──────────────────────────────────────────────────────
        st.divider()
        loaded_name = st.session_state.get("run_name", "")
        save_col1, save_col2, save_col3 = st.columns([3, 1, 3])
        with save_col1:
            run_name_input = st.text_input(
                "Save this run as…",
                value=loaded_name,
                placeholder="e.g. 27/05 Release Run",
                label_visibility="collapsed",
            )
        with save_col2:
            if st.button("💾 Save", disabled=not run_name_input.strip()):
                rname = run_name_input.strip()
                save_run(rname, results, resolved, threshold)
                st.session_state["run_name"] = rname
                open_games = [r for r in not_found_results if r["game_name"] not in resolved]
                for r in open_games:
                    add_to_watchlist(
                        game_name=r["game_name"],
                        provider=r["provider"],
                        run_name=rname,
                        threshold=threshold,
                    )
                msg = f"Run **{rname}** saved!"
                if open_games:
                    msg += f" &nbsp; 👁 {len(open_games)} not-found game(s) added to watch list."
                st.success(msg)
                st.rerun()
        with save_col3:
            if loaded_name:
                st.markdown(f"<span style='color:#7a9cc8;font-size:0.85rem'>Currently viewing: <b style='color:#c8d8f0'>{loaded_name}</b></span>", unsafe_allow_html=True)

        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Submitted", len(results))
        m2.metric("Matched",   len(found_results))
        m3.metric("Resolved",  len(resolved))
        m4.metric("Not Found", len(still_open))

        st.divider()

        watched_games: set[str] = {e["game_name"] for e in get_watchlist()}

        # Custom tabs — persisted in session state so reruns never reset position
        if "active_tab" not in st.session_state:
            st.session_state["active_tab"] = "matched"

        t1_label = f"✅ Matched & Resolved ({len(found_results) + len(resolved)})"
        t2_label = f"❌ Not Found ({len(still_open)})"

        tc1, tc2 = st.columns(2)
        with tc1:
            if st.button(t1_label, use_container_width=True,
                         type="primary" if st.session_state["active_tab"] == "matched" else "secondary"):
                st.session_state["active_tab"] = "matched"
                st.rerun()
        with tc2:
            if st.button(t2_label, use_container_width=True,
                         type="primary" if st.session_state["active_tab"] == "not_found" else "secondary"):
                st.session_state["active_tab"] = "not_found"
                st.rerun()

        st.markdown("<div style='border-top:2px solid #1a3a6e;margin-bottom:16px'></div>", unsafe_allow_html=True)

        # ── Tab 1 ─────────────────────────────────────────────────────────────
        if st.session_state["active_tab"] == "matched":
            rows = []
            for r in found_results:
                ex   = extras.get(r["game_name"], {})
                norm = provider_norm.get(r["game_name"], {})
                prov = norm.get("canonical", r["provider"])
                flag = "⚠️ " if norm.get("flagged") else ""
                rows.append({
                    "Provider Name":          flag + prov,
                    "Provider Platform Name": r["manufacturer"],
                    "Game Name":              r["game_name"],
                    "Product":                ex.get("product", ""),
                    "Game Category":          ex.get("game_category", ""),
                    "HGC Code":               r["hgc_code"],
                    "Source":                 "Auto-matched",
                })
            for game_name, pick in resolved.items():
                if pick.get("status") == "not_in_registry":
                    continue
                ex   = extras.get(game_name, {})
                norm = provider_norm.get(game_name, {})
                prov = norm.get("canonical", pick["provider"])
                flag = "⚠️ " if norm.get("flagged") else ""
                rows.append({
                    "Provider Name":          flag + prov,
                    "Provider Platform Name": pick["manufacturer"],
                    "Game Name":              game_name,
                    "Product":                ex.get("product", ""),
                    "Game Category":          ex.get("game_category", ""),
                    "HGC Code":               pick["hgc_code"],
                    "Source":                 "Manually resolved",
                })

            # Collect "Not Yet In Registry" entries for the expander below
            not_in_registry_entries = [
                {"Game Name": gn, "Provider": pick.get("provider", "")}
                for gn, pick in resolved.items()
                if pick.get("status") == "not_in_registry"
            ]

            if rows:
                df_all = pd.DataFrame(rows)

                # ── Improvement 1: Search/filter ──────────────────────────────
                search_term = st.text_input(
                    "Search games…",
                    key="match_search",
                    placeholder="Filter by Game Name, Provider, HGC Code, or Manufacturer…",
                )
                df_display = df_all
                if search_term.strip():
                    mask = (
                        df_all["Game Name"].str.contains(search_term, case=False, na=False) |
                        df_all["Provider Name"].str.contains(search_term, case=False, na=False) |
                        df_all["Provider Platform Name"].str.contains(search_term, case=False, na=False) |
                        df_all["HGC Code"].str.contains(search_term, case=False, na=False)
                    )
                    df_display = df_all[mask]
                st.caption(f"{len(df_display)} of {len(df_all)} games")

                df_display = df_display.copy()
                df_display["Source"] = df_display["Source"].replace(
                    {"Manually resolved": "✏️ Manually resolved", "Auto-matched": "🤖 Auto-matched"}
                )
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                _tsv = df_display.to_csv(index=False, sep="\t")
                with st.expander("📋 Copy to clipboard (paste into Google Sheets)"):
                    st.caption("Click inside the box → Ctrl+A / Cmd+A → Ctrl+C / Cmd+C → paste into Google Sheets")
                    st.text_area("", value=_tsv, height=200, label_visibility="collapsed", key="copy_area")

                # Append Not Yet In Registry rows (no HGC code — for compliance)
                nir_rows = [
                    {
                        "Provider Name":          pick["provider"],
                        "Provider Platform Name": "",
                        "Game Name":              game_name,
                        "Product":                extras.get(game_name, {}).get("product", ""),
                        "Game Category":          extras.get(game_name, {}).get("game_category", ""),
                        "HGC Code":               "NOT YET IN REGISTRY",
                    }
                    for game_name, pick in resolved.items()
                    if pick.get("status") == "not_in_registry"
                ]
                nir_rows += [
                    {
                        "Provider Name":          r["provider"],
                        "Provider Platform Name": "",
                        "Game Name":              r["game_name"],
                        "Product":                extras.get(r["game_name"], {}).get("product", ""),
                        "Game Category":          extras.get(r["game_name"], {}).get("game_category", ""),
                        "HGC Code":               "NOT YET IN REGISTRY",
                    }
                    for r in still_open
                ]
                _export_cols = ["Provider Name", "Provider Platform Name", "Game Name", "Product", "Game Category", "HGC Code"]
                df_export = pd.concat(
                    [df_all[_export_cols], pd.DataFrame(nir_rows)[_export_cols]],
                    ignore_index=True,
                ) if nir_rows else df_all[_export_cols]

                run_label = st.session_state.get("run_name", "hgc_results")
                dl_name   = run_label.replace("/", "-").replace(" ", "_") + ".csv"
                st.download_button(
                    "⬇️ Download full list (matched + not yet in registry)",
                    data=df_export.to_csv(index=False).encode("utf-8-sig"),
                    file_name=dl_name,
                    mime="text/csv",
                )
            else:
                st.info("No matched results yet.")

            # ── Improvement 3: Not Yet In Registry expander ───────────────────────
            if not_in_registry_entries:
                with st.expander(f"🚫 Not Yet In Registry ({len(not_in_registry_entries)})", expanded=False):
                    nir_df = pd.DataFrame(not_in_registry_entries)
                    for idx, nir_row in nir_df.iterrows():
                        col_a, col_b = st.columns([5, 1])
                        with col_a:
                            st.markdown(
                                f"<span style='color:#c8d8f0;font-weight:600'>{nir_row['Game Name']}</span>"
                                f"<span style='color:#7a9cc8;font-size:0.85rem'> · {nir_row['Provider']}</span>",
                                unsafe_allow_html=True,
                            )
                        with col_b:
                            if st.button("↩ Restore", key=f"restore_nir_{nir_row['Game Name']}"):
                                resolved.pop(nir_row["Game Name"], None)
                                st.session_state["resolved"] = resolved
                                st.session_state["active_tab"] = "matched"
                                if st.session_state.get("run_name"):
                                    save_run(st.session_state["run_name"], results, resolved, threshold)
                                st.rerun()

        # ── Tab 2 ─────────────────────────────────────────────────────────────
        if st.session_state["active_tab"] == "not_found":
            if not still_open:
                st.success("All unmatched games have been resolved!")
                if st.session_state.get("run_name"):
                    if st.button("💾 Save progress"):
                        save_run(st.session_state["run_name"], results, resolved, threshold)
                        st.success("Progress saved!")
            else:
                sc1, sc2 = st.columns([5, 1])
                with sc1:
                    st.markdown(f"Select the correct registry entry for each game, then click **Resolve**. &nbsp; <span style='color:#7a9cc8'>{len(still_open)} remaining</span>", unsafe_allow_html=True)
                with sc2:
                    if st.session_state.get("run_name") and st.button("💾 Save progress"):
                        save_run(st.session_state["run_name"], results, resolved, threshold)
                        st.success("Saved!")

                for r in still_open:
                    alts        = r.get("alternatives", [])
                    all_options = []
                    if r["hgc_code"]:
                        all_options.append({
                            "matched_title": r["matched_title"],
                            "hgc_code":      r["hgc_code"],
                            "manufacturer":  r["manufacturer"],
                            "operator":      r.get("operator", ""),
                            "confidence":    r["confidence"],
                        })
                    all_options.extend(alts[:5])

                    is_watched     = r["game_name"] in watched_games
                    expander_label = f"**{r['game_name']}** · {r['provider']}" + ("  👁" if is_watched else "")

                    with st.expander(expander_label):
                        if is_watched:
                            st.markdown(
                                "<span style='background:#0d3880;color:#a8c8f0;border-radius:10px;"
                                "padding:2px 10px;font-size:0.75rem;font-weight:600'>"
                                "👁 On watch list — will auto-resolve when found</span>",
                                unsafe_allow_html=True,
                            )
                        if not all_options:
                            st.write("No close matches found in the registry.")
                            continue

                        option_labels = [
                            f"{o['matched_title']}  —  {o.get('manufacturer', '')}  —  {o['hgc_code']}  ({o['confidence']}%)"
                            for o in all_options
                        ]

                        choice = st.radio(
                            "Pick the correct match:",
                            options=range(len(option_labels)),
                            format_func=lambda i: option_labels[i],
                            key=f"radio_{r['game_name']}",
                            index=None,
                        )

                        resolve_col, nir_col = st.columns([1, 1])
                        with resolve_col:
                            if st.button("Resolve ✓", key=f"btn_{r['game_name']}", disabled=choice is None):
                                picked = all_options[choice]
                                ex = extras.get(r["game_name"], {})
                                resolved[r["game_name"]] = {
                                    "provider":       r["provider"],
                                    "product":        ex.get("product", ""),
                                    "game_category":  ex.get("game_category", ""),
                                    "hgc_code":       picked["hgc_code"],
                                    "matched_title":  picked["matched_title"],
                                    "manufacturer":   picked["manufacturer"],
                                    "operator":       picked.get("operator", ""),
                                }
                                # Update provider learning map with manual resolution
                                if r.get("provider") and picked.get("manufacturer"):
                                    pm = load_provider_map()
                                    pm[r["provider"]] = picked["manufacturer"]
                                    save_provider_map(pm)
                                st.session_state["resolved"]   = resolved
                                st.session_state["active_tab"] = "not_found"
                                if st.session_state.get("run_name"):
                                    save_run(st.session_state["run_name"], results, resolved, threshold)
                                st.rerun()
                        with nir_col:
                            if st.button("🚫 Not Yet In Registry", key=f"nir_{r['game_name']}"):
                                ex = extras.get(r["game_name"], {})
                                resolved[r["game_name"]] = {
                                    "status":         "not_in_registry",
                                    "provider":       r["provider"],
                                    "product":        ex.get("product", ""),
                                    "game_category":  ex.get("game_category", ""),
                                    "hgc_code":       None,
                                    "matched_title":  None,
                                    "manufacturer":   None,
                                    "operator":       None,
                                }
                                # Remove from watchlist if present
                                current_run_name = st.session_state.get("run_name", "")
                                if current_run_name:
                                    remove_from_watchlist(r["game_name"], current_run_name)
                                st.session_state["resolved"]   = resolved
                                st.session_state["active_tab"] = "not_found"
                                if st.session_state.get("run_name"):
                                    save_run(st.session_state["run_name"], results, resolved, threshold)
                                st.rerun()

# ── Page: Not Yet In Registry (cross-run view) ────────────────────────────────
with page_nyr:
    all_runs_nyr = load_runs()
    nyr_rows = []

    for run in all_runs_nyr:
        run_name    = run.get("name", "Unknown")
        saved_dt    = datetime.fromisoformat(run["saved_at"]).strftime("%d %b %Y")
        threshold_r = run.get("threshold", 88)
        results_r   = run.get("results", [])
        resolved_r  = run.get("resolved", {})

        # Games explicitly marked Not Yet In Registry
        for game_name, pick in resolved_r.items():
            if pick.get("status") == "not_in_registry":
                nyr_rows.append({
                    "Game Name":   game_name,
                    "Provider":    pick.get("provider", ""),
                    "Release Run": run_name,
                    "Run Date":    saved_dt,
                    "Status":      "🚫 Marked Not Yet In Registry",
                })

        # Games still open (not found, not resolved, not dismissed)
        not_found_r = [
            r for r in results_r
            if (r.get("review") or r.get("confidence", 0) < threshold_r)
            and r["game_name"] not in resolved_r
        ]
        for r in not_found_r:
            nyr_rows.append({
                "Game Name":   r["game_name"],
                "Provider":    r.get("provider", ""),
                "Release Run": run_name,
                "Run Date":    saved_dt,
                "Status":      "⏳ Still Open",
            })

    if not nyr_rows:
        st.info("No games flagged as Not Yet In Registry across any saved run.")
    else:
        df_nyr = pd.DataFrame(nyr_rows)

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            run_opts   = ["All runs"] + sorted(df_nyr["Release Run"].unique().tolist())
            run_filter = st.selectbox("Filter by Release Run", run_opts, key="nyr_run")
        with fc2:
            status_opts   = ["All statuses"] + sorted(df_nyr["Status"].unique().tolist())
            status_filter = st.selectbox("Filter by Status", status_opts, key="nyr_status")
        with fc3:
            search_nyr = st.text_input("Search game…", key="nyr_search", placeholder="Game name or provider")

        df_view = df_nyr.copy()
        if run_filter != "All runs":
            df_view = df_view[df_view["Release Run"] == run_filter]
        if status_filter != "All statuses":
            df_view = df_view[df_view["Status"] == status_filter]
        if search_nyr.strip():
            df_view = df_view[
                df_view["Game Name"].str.contains(search_nyr, case=False, na=False) |
                df_view["Provider"].str.contains(search_nyr, case=False, na=False)
            ]

        m1, m2, m3 = st.columns(3)
        m1.metric("Total", len(df_view))
        m2.metric("Marked Not Yet In Registry", (df_view["Status"] == "🚫 Marked Not Yet In Registry").sum())
        m3.metric("Still Open", (df_view["Status"] == "⏳ Still Open").sum())

        st.divider()

        def highlight_nyr(row):
            if "Marked" in row["Status"]:
                return ["background-color: #3d1a1a; color: #f0a0a0"] * len(row)
            return ["background-color: #1a2d3d; color: #a0c8f0"] * len(row)

        st.dataframe(
            df_view.style.apply(highlight_nyr, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download for compliance",
            data=df_view.to_csv(index=False).encode("utf-8-sig"),
            file_name="not_yet_in_registry.csv",
            mime="text/csv",
        )
