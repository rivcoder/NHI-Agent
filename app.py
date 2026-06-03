import os
import time
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="NHI Governance Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Premium Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .stApp {
        background-color: #0b0e14;
        color: #c9d1d9;
    }
    
    section[data-testid="stSidebar"] {
        background-color: #07090e !important;
        border-right: 1px solid #21262d;
    }
    
    .stTextInput>div>div>input {
        background-color: #161b22 !important;
        color: #c9d1d9 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
    }
    .stTextInput>div>div>input:focus {
        border-color: #58a6ff !important;
        box-shadow: 0 0 0 3px rgba(88,166,255,0.15) !important;
    }
    
    div.stButton > button {
        border-radius: 6px !important;
        font-weight: 500 !important;
    }
    
    /* Code block styling */
    pre, code {
        font-family: 'JetBrains Mono', monospace !important;
    }
</style>
""", unsafe_allow_html=True)


# Imports
try:
    from scanner import scan_gitlab_repo, score_risk_with_gemini
    SCANNER_AVAILABLE = True
except ImportError:
    SCANNER_AVAILABLE = False

try:
    from db import save_scan, get_recent_scans, get_nhi_index, get_drift_summary, get_scan_history_chart, seed_demo_data
    MONGO_AVAILABLE = True
except Exception:
    MONGO_AVAILABLE = False

RISK_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
RISK_COLOR = {"CRITICAL": "#ff4444", "HIGH": "#ff8c00", "MEDIUM": "#e6b800", "LOW": "#2fcc40"}

def render_card(title, value, border_color, text_color):
    return f"""
    <div style="background: rgba(22, 27, 34, 0.6); 
                border: 1px solid {border_color}; 
                border-radius: 8px; 
                padding: 15px; 
                text-align: center; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.25);
                backdrop-filter: blur(8px);
                margin-bottom: 15px;">
      <p style="color: #8b949e; margin: 0; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">{title}</p>
      <p style="color: {text_color}; margin: 5px 0 0 0; font-size: 32px; font-weight: 700;">{value}</p>
    </div>
    """

# Session state initialization
for k, v in [("results", []), ("scan_meta", {}), ("active_tab", "scan")]:
    if k not in st.session_state:
        st.session_state[k] = v

# Sidebar configuration
with st.sidebar:
    st.title("🛡️ NHI Governance")
    st.caption("Non-Human Identity scanner · Gemini-powered risk scoring")
    st.divider()

    tab = st.radio("View", ["Live Scan", "History & Drift", "NHI Index"], label_visibility="collapsed")

    st.divider()
    if tab == "Live Scan":
        repo_url     = st.text_input("GitLab repo URL", placeholder="https://gitlab.com/user/repo")
        gitlab_token = st.text_input("GitLab token (optional)", type="password", placeholder="glpat-xxxx")
        risk_filter  = st.multiselect("Show risk levels", ["CRITICAL","HIGH","MEDIUM","LOW"],
                                      default=["CRITICAL","HIGH","MEDIUM","LOW"])
        st.divider()
        col_a, col_b = st.columns(2)
        scan_btn = col_a.button("▶ Scan", use_container_width=True, type="primary")
        demo_btn = col_b.button("🎭 Demo", use_container_width=True)
    else:
        scan_btn = demo_btn = False
        repo_filter = st.text_input("Filter by repo", placeholder="https://gitlab.com/...")
        risk_filter = ["CRITICAL","HIGH","MEDIUM","LOW"]

    st.divider()
    if MONGO_AVAILABLE:
        st.success("MongoDB connected", icon="🟢")
        if st.button("Seed demo data", use_container_width=True):
            with st.spinner("Seeding 7-day story..."):
                seed_demo_data()
            st.success("Demo data seeded!")
    else:
        st.warning("MongoDB offline — set MONGO_URI in .env", icon="🔴")

# Header section
st.title("🛡️ NHI Governance Agent")
st.caption("Detect · Score · Track · Remediate Non-Human Identities across GitLab repos")
st.divider()

# --- Tab: Live Scan ---
if tab == "Live Scan":

    is_demo = False
    if demo_btn:
        repo_url = "demo"
        is_demo  = True

    if (scan_btn or demo_btn):
        if not repo_url:
            st.error("Enter a GitLab repo URL.")
        elif not SCANNER_AVAILABLE:
            st.error("scanner.py not found in this directory.")
        else:
            with st.spinner("Scanning repo..." if not is_demo else "Running demo scan..."):
                t0  = time.time()
                raw = scan_gitlab_repo(repo_url, None if is_demo else (gitlab_token or None))

            if not raw:
                st.warning("No NHI patterns found.")
                st.session_state.results = []
            else:
                with st.spinner(f"Scoring {len(raw)} findings with Gemini..."):
                    scored = score_risk_with_gemini(raw)

                elapsed = round(time.time() - t0, 1)
                st.session_state.results  = scored
                st.session_state.scan_meta = {
                    "repo": "Demo: acme-payments" if is_demo else repo_url,
                    "elapsed": elapsed,
                    "total": len(scored),
                }

                if MONGO_AVAILABLE:
                    try:
                        scan_id = save_scan(repo_url, scored)
                        st.success(f"Scan complete · {len(scored)} findings · {elapsed}s · saved to MongoDB `{scan_id[:8]}...`")
                    except Exception as e:
                        st.success(f"Scan complete · {len(scored)} findings · {elapsed}s")
                        st.warning(f"MongoDB save failed: {e}")
                else:
                    st.success(f"Scan complete · {len(scored)} findings · {elapsed}s")

    results = st.session_state.results
    meta    = st.session_state.scan_meta

    if results:
        critical = [r for r in results if r.get("risk") == "CRITICAL"]
        high     = [r for r in results if r.get("risk") == "HIGH"]
        medium   = [r for r in results if r.get("risk") == "MEDIUM"]
        low      = [r for r in results if r.get("risk") == "LOW"]

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.markdown(render_card("Total", meta.get("total", len(results)), "#30363d", "#c9d1d9"), unsafe_allow_html=True)
        c2.markdown(render_card("Critical", len(critical), "#ff4444", "#ff4444"), unsafe_allow_html=True)
        c3.markdown(render_card("High", len(high), "#ff8c00", "#ff8c00"), unsafe_allow_html=True)
        c4.markdown(render_card("Medium", len(medium), "#e6b800", "#e6b800"), unsafe_allow_html=True)
        c5.markdown(render_card("Low", len(low), "#2fcc40", "#2fcc40"), unsafe_allow_html=True)


        if critical:
            st.error("### ⚠️ Immediate remediation required")
            for r in critical:
                f = r["raw"]
                st.markdown(f"→ `{f['file']}` line **{f['line']}** · pattern: `{f['pattern']}`")

        st.divider()
        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.subheader("Findings")
            filtered = sorted(
                [r for r in results if r.get("risk","UNKNOWN") in risk_filter],
                key=lambda r: RISK_ORDER.get(r.get("risk","UNKNOWN"), 5)
            )
            for r in filtered:
                f    = r["raw"]
                risk = r.get("risk","UNKNOWN")
                icon = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢"}.get(risk,"⚪")
                with st.expander(f"{icon} {risk} · {f['file']}:{f['line']}"):
                    st.code(f["content"], language="python")
                    st.markdown(f"**Type:** {r.get('type','—')}  \n**Reason:** {r.get('reason','—')}")
                    st.info(f"**Action:** {r.get('action','—')}")

        with col_r:
            st.subheader("Export")
            rows = [{"File": r["raw"]["file"], "Line": r["raw"]["line"],
                     "Pattern": r["raw"]["pattern"], "Risk": r.get("risk","UNKNOWN"),
                     "Type": r.get("type",""), "Action": r.get("action","")}
                    for r in results]
            df = pd.DataFrame(rows)
            st.dataframe(df[["File","Line","Risk","Pattern"]], use_container_width=True, height=240)
            st.download_button("⬇ Download CSV", df.to_csv(index=False),
                               "nhi_findings.csv", "text/csv", use_container_width=True)
            st.subheader("Risk breakdown")
            st.bar_chart(df["Risk"].value_counts(), height=180)
    else:
        st.info("Enter a repo URL and click **▶ Scan**, or click **🎭 Demo** to see sample findings.")

# --- Tab: History & Drift ---
elif tab == "History & Drift":
    if not MONGO_AVAILABLE:
        st.warning("MongoDB not connected. Set MONGO_URI in .env and restart.")
        st.stop()

    repo = repo_filter if repo_filter else None

    # ── Drift alerts ──────────────────────────────────────────────────────────
    drifts = get_drift_summary(repo=repo)
    if drifts:
        st.subheader(f"⚡ Risk drift detected — {len(drifts)} NHI(s) changed level")
        for d in drifts:
            arrow = "↑" if RISK_ORDER.get(d["to"],5) < RISK_ORDER.get(d["from"],5) else "↓"
            color = "error" if d["to"] == "CRITICAL" else "warning"
            getattr(st, color)(
                f"{arrow} `{d['file']}` · `{d['pattern']}` changed **{d['from']} → {d['to']}**"
            )
    else:
        st.success("No risk drift detected across tracked NHIs.")

    st.divider()

    # ── Scan history chart ────────────────────────────────────────────────────
    st.subheader("Scan history — risk counts over time")
    demo_repo = "https://gitlab.com/demo/acme-payments"
    chart_repo = repo or demo_repo
    history = get_scan_history_chart(repo=chart_repo)

    if history:
        df_hist = pd.DataFrame(history).set_index("date")
        st.line_chart(df_hist[["critical","high","medium","low"]], height=260,
                      color=["#ff4444","#ff8c00","#e6b800","#2fcc40"])
        st.caption(f"Repo: {chart_repo}")
    else:
        st.info("No scan history yet. Run scans or click **Seed demo data** in the sidebar.")

    st.divider()

    # ── Recent scans table ────────────────────────────────────────────────────
    st.subheader("Recent scans")
    recent = get_recent_scans(repo=repo, limit=15)
    if recent:
        rows = []
        for s in recent:
            sm = s.get("summary", {})
            rows.append({
                "Scan ID":  s["_id"][:8] + "...",
                "Repo":     s.get("repo","")[-40:],
                "Time":     str(s.get("scanned_at",""))[:16],
                "Total":    s.get("total", 0),
                "Critical": sm.get("critical", 0),
                "High":     sm.get("high", 0),
                "Medium":   sm.get("medium", 0),
                "Low":      sm.get("low", 0),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=320)
    else:
        st.info("No scans saved yet.")

# --- Tab: NHI Index ---
elif tab == "NHI Index":
    if not MONGO_AVAILABLE:
        st.warning("MongoDB not connected. Set MONGO_URI in .env and restart.")
        st.stop()

    repo  = repo_filter if repo_filter else None
    nhis  = get_nhi_index(repo=repo)

    if not nhis:
        st.info("No NHIs indexed yet. Run scans or seed demo data.")
        st.stop()

    st.subheader(f"Tracked NHIs — {len(nhis)} identities")

    # Summary metrics
    c1,c2,c3,c4 = st.columns(4)
    c1.markdown(render_card("Critical", sum(1 for n in nhis if n.get("current_risk")=="CRITICAL"), "#ff4444", "#ff4444"), unsafe_allow_html=True)
    c2.markdown(render_card("High", sum(1 for n in nhis if n.get("current_risk")=="HIGH"), "#ff8c00", "#ff8c00"), unsafe_allow_html=True)
    c3.markdown(render_card("Medium", sum(1 for n in nhis if n.get("current_risk")=="MEDIUM"), "#e6b800", "#e6b800"), unsafe_allow_html=True)
    c4.markdown(render_card("Low", sum(1 for n in nhis if n.get("current_risk")=="LOW"), "#2fcc40", "#2fcc40"), unsafe_allow_html=True)


    st.divider()

    # Sort by risk
    nhis.sort(key=lambda n: RISK_ORDER.get(n.get("current_risk","UNKNOWN"), 5))

    for nhi in nhis:
        risk  = nhi.get("current_risk","UNKNOWN")
        icon  = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢"}.get(risk,"⚪")
        hist  = nhi.get("history", [])
        drift = ""
        if len(hist) >= 2 and hist[-1]["risk"] != hist[-2]["risk"]:
            drift = f" ⚡ drifted {hist[-2]['risk']} → {hist[-1]['risk']}"

        with st.expander(f"{icon} {risk} · {nhi.get('file','?')} · `{nhi.get('pattern','?')}`{drift}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Type:** {nhi.get('type','—')}")
                st.markdown(f"**First seen:** {str(nhi.get('first_seen','—'))[:16]}")
                st.markdown(f"**Last seen:** {str(nhi.get('last_seen','—'))[:16]}")
                st.markdown(f"**Scan count:** {len(hist)}")
            with col2:
                st.info(f"**Action:** {nhi.get('action','—')}")

            # Mini drift chart
            if len(hist) >= 2:
                df_drift = pd.DataFrame([
                    {"scan": i+1, "risk_score": 3 - RISK_ORDER.get(h["risk"],3)}
                    for i, h in enumerate(hist)
                ]).set_index("scan")
                st.line_chart(df_drift, height=100, use_container_width=True)
                st.caption("Risk score over time (higher = more severe)")
