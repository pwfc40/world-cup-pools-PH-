import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="World Cup 2026 Pools", page_icon="🏆", layout="wide")


def secret(name: str, default: str) -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

ADMIN_PASSWORD = secret("ADMIN_PASSWORD", "admin")
ENTRY_CODE = secret("ENTRY_CODE", "worldcup")
PLAYER_VIEW_PASSWORD = secret("PLAYER_VIEW_PASSWORD", "leaderboard")

FILES = {
    "pools": "pools.json",
    "submissions": "submissions.csv",
    "nation_results": "nation_results.csv",
    "player_results": "player_results.csv",
    "ko_results": "ko_results.csv",
    "config": "admin_config.json",
}

SUBMISSION_COLUMNS = [
    "participant", "paid", "notes",
    "Nation A", "Nation B", "Nation C", "Nation D", "Nation E", "Nation F",
    "Player Pool 1", "Player Pool 2", "Player Pool 3", "Player Pool 4",
    "Player Pool 5", "Player Pool 6", "Player Pool 7", "Player Pool 8",
    "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Bet 1", "Bet 2", "Bet 3", "Bet 4",
]


def load_json_file(filename: str, fallback):
    path = DATA_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return fallback


def save_json_file(obj, filename: str):
    with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_csv(filename: str, columns=None) -> pd.DataFrame:
    path = DATA_DIR / filename
    if path.exists():
        df = pd.read_csv(path, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=columns or [])
    if columns:
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        df = df[columns + [c for c in df.columns if c not in columns]]
    return df


def save_csv(df: pd.DataFrame, filename: str):
    df.to_csv(DATA_DIR / filename, index=False)


DATA = load_json_file(FILES["pools"], {"nations": [], "players": [], "scoring": {}, "ko_questions": []})
SCORING = DATA.get("scoring", {})
CONFIG = load_json_file(FILES["config"], {"nation_player_entries_open": True, "ko_entries_open": False, "show_leaderboard": True})


def to_num(s, default=0):
    return pd.to_numeric(s, errors="coerce").fillna(default)


def as_bool(s):
    return to_num(s).clip(lower=0, upper=1)


def normalize(value: str) -> str:
    return str(value or "").strip().lower()


def calc_nation_results(nation_results: pd.DataFrame) -> pd.DataFrame:
    n = nation_results.copy()
    ns = SCORING.get("nation", {})
    defaults = ["wins", "draws", "clean_sheets", "games_3_plus_scored", "games_3_plus_conceded", "wins_vs_pool_a", "reached_last32", "reached_last16", "reached_qf", "reached_semi", "reached_final", "winner", "multiplier"]
    for c in defaults:
        if c not in n.columns:
            n[c] = 0
    n["base_points"] = (
        to_num(n["wins"]) * ns.get("win", 4)
        + to_num(n["draws"]) * ns.get("draw", 2)
        + to_num(n["clean_sheets"]) * ns.get("clean_sheet", 2)
        + to_num(n["games_3_plus_scored"]) * ns.get("score_3_plus", 2)
        + to_num(n["games_3_plus_conceded"]) * ns.get("concede_3_plus", -2)
        + to_num(n["wins_vs_pool_a"]) * ns.get("beat_pool_a", 4)
        + as_bool(n["reached_last32"]) * ns.get("last32", 5)
        + as_bool(n["reached_last16"]) * ns.get("last16", 8)
        + as_bool(n["reached_qf"]) * ns.get("qf", 10)
        + as_bool(n["reached_semi"]) * ns.get("semi", 12)
        + as_bool(n["reached_final"]) * ns.get("final", 15)
        + as_bool(n["winner"]) * ns.get("winner", 20)
    )
    n["total_points"] = (n["base_points"] * to_num(n["multiplier"], 1)).round(1)
    return n


def goal_points(position: str) -> int:
    ps = SCORING.get("player", {})
    pos = str(position).upper()
    if pos == "MID":
        return ps.get("goal_mid", 6)
    if pos == "DEF":
        return ps.get("goal_def", 8)
    return ps.get("goal_fwd", 5)


def clean_sheet_points(position: str) -> int:
    ps = SCORING.get("player", {})
    pos = str(position).upper()
    if pos == "MID":
        return ps.get("clean_sheet_mid", 1)
    if pos == "DEF":
        return ps.get("clean_sheet_def", 3)
    return 0


def calc_player_results(player_results: pd.DataFrame) -> pd.DataFrame:
    p = player_results.copy()
    ps = SCORING.get("player", {})
    for c in ["goals", "assists", "clean_sheets", "motm", "yellow_cards", "red_cards", "missed_penalties", "multiplier"]:
        if c not in p.columns:
            p[c] = 0
    if "position" not in p.columns:
        p["position"] = "FWD"
    gp = p["position"].map(goal_points).fillna(ps.get("goal_fwd", 5))
    csp = p["position"].map(clean_sheet_points).fillna(0)
    p["base_points"] = (
        to_num(p["goals"]) * gp
        + to_num(p["assists"]) * ps.get("assist", 2)
        + to_num(p["clean_sheets"]) * csp
        + to_num(p["motm"]) * ps.get("motm", 5)
        + to_num(p["yellow_cards"]) * ps.get("yellow", -1)
        + to_num(p["red_cards"]) * ps.get("red", -3)
        + to_num(p["missed_penalties"]) * ps.get("missed_penalty", -2)
    )
    p["total_points"] = (p["base_points"] * to_num(p["multiplier"], 1)).round(1)
    return p


def score_range_guess(guess, actual):
    try:
        diff = abs(int(float(guess)) - int(float(actual)))
    except Exception:
        return 0
    if diff == 0: return 20
    if diff <= 2: return 10
    if diff <= 4: return 6
    if diff <= 6: return 3
    return 0


def score_draws_guess(guess, actual):
    try:
        diff = abs(int(float(guess)) - int(float(actual)))
    except Exception:
        return 0
    if diff == 0: return 20
    if diff <= 2: return 10
    if diff <= 4: return 6
    if diff <= 6: return 4
    return 0


def calc_ko_points(submissions: pd.DataFrame, ko_results: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"participant": submissions.get("participant", pd.Series(dtype=str))})
    if ko_results.empty:
        out["ko_points"] = 0
        return out
    kr = ko_results.iloc[0].to_dict()
    q1_ans = normalize(kr.get("Q1_answer", ""))
    q1_l16 = {normalize(x) for x in str(kr.get("Q1_last16_list", "")).split(",") if x.strip()}
    vals = []
    for _, r in submissions.iterrows():
        total = 0
        q1 = normalize(r.get("Q1", ""))
        if q1:
            if q1_ans and q1 == q1_ans:
                total += 20
            elif q1 in q1_l16:
                total += 6
        total += score_range_guess(r.get("Q2", ""), kr.get("Q2_goals_r32", ""))
        total += score_range_guess(r.get("Q3", ""), kr.get("Q3_goals_rest_ko", ""))
        total += score_draws_guess(r.get("Q4", ""), kr.get("Q4_90min_draws", ""))
        total += score_draws_guess(r.get("Q5", ""), kr.get("Q5_penalty_shootouts", ""))
        if normalize(r.get("Q6", "")) and normalize(r.get("Q6", "")) == normalize(kr.get("Q6_top_ko_goals_nation", "")):
            total += 20
        bs = SCORING.get("bets", {})
        for i in range(1, 5):
            pick = normalize(r.get(f"Bet {i}", ""))
            result = normalize(kr.get(f"Bet {i} result", ""))
            if pick and result:
                total += bs.get("correct", 8) if pick == result else bs.get("wrong", -4)
        vals.append(total)
    out["ko_points"] = vals
    return out


def make_leaderboard():
    subs = load_csv(FILES["submissions"], SUBMISSION_COLUMNS)
    nr = calc_nation_results(load_csv(FILES["nation_results"]))
    pr = calc_player_results(load_csv(FILES["player_results"]))
    ko = calc_ko_points(subs, load_csv(FILES["ko_results"]))
    rows = []
    for _, s in subs.iterrows():
        if not str(s.get("participant", "")).strip():
            continue
        nation_total = 0.0
        for pool in list("ABCDEF"):
            pick = str(s.get(f"Nation {pool}", "")).strip()
            pts = nr.loc[nr.get("nation", pd.Series(dtype=str)).astype(str).str.lower() == pick.lower(), "total_points"]
            nation_total += float(pts.iloc[0]) if len(pts) else 0
        player_total = 0.0
        for pool in range(1, 9):
            pick = str(s.get(f"Player Pool {pool}", "")).strip()
            pts = pr.loc[pr.get("player", pd.Series(dtype=str)).astype(str).str.lower() == pick.lower(), "total_points"]
            player_total += float(pts.iloc[0]) if len(pts) else 0
        ko_pts = 0.0
        if not ko.empty and (ko["participant"] == s["participant"]).any():
            ko_pts = float(ko.loc[ko["participant"] == s["participant"], "ko_points"].iloc[0])
        rows.append({
            "Participant": s["participant"],
            "Nation points": round(nation_total, 1),
            "Player points": round(player_total, 1),
            "KO/Bets points": round(ko_pts, 1),
            "Total": round(nation_total + player_total + ko_pts, 1),
            "Paid": s.get("paid", ""),
        })
    lb = pd.DataFrame(rows)
    if lb.empty:
        return pd.DataFrame(columns=["Rank", "Participant", "Nation points", "Player points", "KO/Bets points", "Total", "Paid"])
    lb = lb.sort_values("Total", ascending=False).reset_index(drop=True)
    lb.insert(0, "Rank", range(1, len(lb) + 1))
    return lb


def pools_by(key: str, pool_col: str = "pool"):
    rows = DATA.get(key, [])
    return sorted({str(r.get(pool_col, "")) for r in rows if str(r.get(pool_col, ""))})


def option_list(rows, pool, label):
    return [r[label] for r in rows if str(r.get("pool")) == str(pool)]


def require_admin() -> bool:
    if st.session_state.get("admin_ok"):
        return True
    with st.form("admin_login"):
        st.subheader("Admin login")
        pw = st.text_input("Admin password", type="password")
        ok = st.form_submit_button("Unlock admin")
    if ok and pw == ADMIN_PASSWORD:
        st.session_state["admin_ok"] = True
        st.rerun()
    elif ok:
        st.error("Incorrect admin password.")
    return False


def require_player_view() -> bool:
    if st.session_state.get("player_ok") or CONFIG.get("show_leaderboard", True):
        return True
    with st.form("player_login"):
        st.subheader("Leaderboard locked")
        pw = st.text_input("Player view password", type="password")
        ok = st.form_submit_button("View leaderboard")
    if ok and pw == PLAYER_VIEW_PASSWORD:
        st.session_state["player_ok"] = True
        st.rerun()
    elif ok:
        st.error("Incorrect password.")
    return False


def build_backup_zip() -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in FILES.values():
            path = DATA_DIR / name
            if path.exists():
                z.write(path, arcname=f"data/{name}")
    mem.seek(0)
    return mem.getvalue()


def restore_backup(uploaded):
    with zipfile.ZipFile(uploaded) as z:
        for member in z.namelist():
            filename = Path(member).name
            if filename in FILES.values():
                (DATA_DIR / filename).write_bytes(z.read(member))


st.title("🏆 World Cup 2026 Pools")
st.caption("Private web app for entries, scoring and the live leaderboard.")

page = st.sidebar.radio(
    "Menu",
    ["Home", "Submit nation/player picks", "Submit KO questions", "Leaderboard", "Rules", "Admin"],
)

if page == "Home":
    st.subheader("Game status")
    c1, c2, c3 = st.columns(3)
    c1.metric("Nation/player entries", "Open" if CONFIG.get("nation_player_entries_open", True) else "Closed")
    c2.metric("KO questions", "Open" if CONFIG.get("ko_entries_open", False) else "Closed")
    c3.metric("Entries", len(load_csv(FILES["submissions"], SUBMISSION_COLUMNS)))
    st.write("Use the sidebar to submit picks, view the leaderboard, or review the scoring rules.")
    st.info("Share the app link privately. Entrants need the entry code to submit picks.")

elif page == "Submit nation/player picks":
    if not CONFIG.get("nation_player_entries_open", True):
        st.warning("Nation and player submissions are currently closed.")
    else:
        with st.form("entry_form"):
            st.subheader("Submit nation and player picks")
            code = st.text_input("Entry code", type="password")
            participant = st.text_input("Your name")
            notes = st.text_input("Notes / email / WhatsApp name", "")
            nation_picks = {}
            st.write("### Nation picks")
            cols = st.columns(3)
            for idx, pool in enumerate(list("ABCDEF")):
                options = [""] + option_list(DATA.get("nations", []), pool, "nation")
                nation_picks[f"Nation {pool}"] = cols[idx % 3].selectbox(f"Nation Pool {pool}", options, key=f"n_{pool}")
            player_picks = {}
            st.write("### Player picks")
            cols = st.columns(4)
            for pool in range(1, 9):
                options = [""] + option_list(DATA.get("players", []), pool, "player")
                player_picks[f"Player Pool {pool}"] = cols[(pool - 1) % 4].selectbox(f"Player Pool {pool}", options, key=f"p_{pool}")
            submit = st.form_submit_button("Submit picks")
        if submit:
            if code != ENTRY_CODE:
                st.error("Incorrect entry code.")
            elif not participant.strip():
                st.error("Please enter your name.")
            elif any(not v for v in nation_picks.values()) or any(not v for v in player_picks.values()):
                st.error("Please make every nation and player selection.")
            else:
                subs = load_csv(FILES["submissions"], SUBMISSION_COLUMNS)
                row = {c: "" for c in SUBMISSION_COLUMNS}
                row.update({"participant": participant.strip(), "paid": "No", "notes": notes.strip()})
                row.update(nation_picks)
                row.update(player_picks)
                if (subs["participant"].astype(str).str.lower() == participant.strip().lower()).any():
                    idx = subs.index[subs["participant"].astype(str).str.lower() == participant.strip().lower()][0]
                    for k, v in row.items():
                        subs.at[idx, k] = v
                    st.success("Your previous entry has been updated.")
                else:
                    subs = pd.concat([subs, pd.DataFrame([row])], ignore_index=True)
                    st.success("Entry submitted.")
                save_csv(subs, FILES["submissions"])

elif page == "Submit KO questions":
    if not CONFIG.get("ko_entries_open", False):
        st.warning("KO question submissions are not open yet.")
    else:
        subs = load_csv(FILES["submissions"], SUBMISSION_COLUMNS)
        names = [""] + sorted([x for x in subs["participant"].astype(str).tolist() if x.strip()])
        with st.form("ko_form"):
            st.subheader("Submit KO questions and bets")
            code = st.text_input("Entry code", type="password")
            participant = st.selectbox("Your name", names)
            nations = [""] + [r["nation"] for r in DATA.get("nations", [])]
            q1 = st.selectbox("Q1: Lowest-ranked team to reach QF", nations)
            q2 = st.number_input("Q2: Total goals in Round of 32", min_value=0, step=1)
            q3 = st.number_input("Q3: Total goals in remaining KO rounds", min_value=0, step=1)
            q4 = st.number_input("Q4: Number of draws after 90 mins", min_value=0, step=1)
            q5 = st.number_input("Q5: Number of penalty shootouts", min_value=0, step=1)
            q6 = st.selectbox("Q6: Nation scoring most KO goals", nations)
            st.write("### Optional bets")
            b1 = st.selectbox("Bet 1", ["", "Yes", "No"])
            b2 = st.selectbox("Bet 2", ["", "Yes", "No"])
            b3 = st.selectbox("Bet 3", ["", "Yes", "No"])
            b4 = st.selectbox("Bet 4", ["", "Yes", "No"])
            submit = st.form_submit_button("Save KO picks")
        if submit:
            if code != ENTRY_CODE:
                st.error("Incorrect entry code.")
            elif not participant:
                st.error("Please select your name.")
            else:
                idx = subs.index[subs["participant"] == participant][0]
                updates = {"Q1": q1, "Q2": q2, "Q3": q3, "Q4": q4, "Q5": q5, "Q6": q6, "Bet 1": b1, "Bet 2": b2, "Bet 3": b3, "Bet 4": b4}
                for k, v in updates.items():
                    subs.at[idx, k] = v
                save_csv(subs, FILES["submissions"])
                st.success("KO picks saved.")

elif page == "Leaderboard":
    if require_player_view():
        lb = make_leaderboard()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entries", len(lb))
        c2.metric("Leader", lb.iloc[0]["Participant"] if len(lb) else "-")
        c3.metric("Top score", lb.iloc[0]["Total"] if len(lb) else 0)
        paid_count = int((load_csv(FILES["submissions"], SUBMISSION_COLUMNS)["paid"].astype(str).str.lower() == "yes").sum())
        c4.metric("Paid", paid_count)
        st.dataframe(lb, use_container_width=True, hide_index=True)
        st.download_button("Download leaderboard CSV", lb.to_csv(index=False).encode("utf-8"), "leaderboard.csv", "text/csv")

elif page == "Rules":
    st.subheader("Rules and scoring")
    c1, c2 = st.columns(2)
    with c1:
        st.write("Nation scoring")
        st.json(SCORING.get("nation", {}))
        st.write("Nation pools")
        st.dataframe(pd.DataFrame(DATA.get("nations", [])), use_container_width=True, hide_index=True)
    with c2:
        st.write("Player scoring")
        st.json(SCORING.get("player", {}))
        st.write("Bet scoring")
        st.json(SCORING.get("bets", {}))
        st.write("Player pools")
        st.dataframe(pd.DataFrame(DATA.get("players", [])), use_container_width=True, hide_index=True)

elif page == "Admin":
    if require_admin():
        st.success("Admin unlocked")
        tabs = st.tabs(["Settings", "Submissions", "Nation scoring", "Player scoring", "KO answers", "Backups"])
        with tabs[0]:
            st.subheader("App settings")
            cfg = CONFIG.copy()
            cfg["nation_player_entries_open"] = st.checkbox("Nation/player entries open", value=bool(cfg.get("nation_player_entries_open", True)))
            cfg["ko_entries_open"] = st.checkbox("KO entries open", value=bool(cfg.get("ko_entries_open", False)))
            cfg["show_leaderboard"] = st.checkbox("Leaderboard public without password", value=bool(cfg.get("show_leaderboard", True)))
            cfg["admin_notes"] = st.text_area("Admin notes", value=str(cfg.get("admin_notes", "")))
            if st.button("Save settings"):
                save_json_file(cfg, FILES["config"])
                st.success("Settings saved. Refresh the app to see changes everywhere.")
        with tabs[1]:
            st.subheader("All submissions")
            df = load_csv(FILES["submissions"], SUBMISSION_COLUMNS)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("Save submissions", key="save_subs"):
                save_csv(edited, FILES["submissions"])
                st.success("Submissions saved.")
        with tabs[2]:
            st.subheader("Nation scoring inputs")
            df = load_csv(FILES["nation_results"])
            edited = st.data_editor(df, use_container_width=True, hide_index=True)
            if st.button("Save nation scoring"):
                save_csv(edited, FILES["nation_results"])
                st.success("Nation scoring saved.")
            st.write("Calculated nation points")
            st.dataframe(calc_nation_results(edited).sort_values("total_points", ascending=False), use_container_width=True, hide_index=True)
        with tabs[3]:
            st.subheader("Player scoring inputs")
            df = load_csv(FILES["player_results"])
            edited = st.data_editor(df, use_container_width=True, hide_index=True)
            if st.button("Save player scoring"):
                save_csv(edited, FILES["player_results"])
                st.success("Player scoring saved.")
            st.write("Calculated player points")
            st.dataframe(calc_player_results(edited).sort_values("total_points", ascending=False), use_container_width=True, hide_index=True)
        with tabs[4]:
            st.subheader("Official KO answers and bet results")
            ko = load_csv(FILES["ko_results"])
            edited = st.data_editor(ko, use_container_width=True, hide_index=True, num_rows="fixed")
            if st.button("Save KO answers"):
                save_csv(edited, FILES["ko_results"])
                st.success("KO answers saved.")
        with tabs[5]:
            st.subheader("Backup and restore")
            st.caption("Download backups regularly. This is important on free hosting.")
            backup_name = f"world_cup_pools_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            st.download_button("Download full data backup", build_backup_zip(), backup_name, "application/zip")
            upload = st.file_uploader("Restore from backup ZIP", type=["zip"])
            if upload and st.button("Restore backup"):
                restore_backup(upload)
                st.success("Backup restored. Refresh the app.")
