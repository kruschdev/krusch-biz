import os
import streamlit as st
import httpx

# Page setup
st.set_page_config(
    page_title="KruschBiz | Sovereign Corporate Intelligence Engine",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8086")
DEFAULT_API_KEY = os.getenv("API_KEY", "")


def get_auth_headers() -> dict:
    """Return authorization headers with configured API key and tenant ID if available."""
    key = st.session_state.get("api_key", DEFAULT_API_KEY)
    headers = {
        "X-Tenant-ID": st.session_state.get("tenant_id", "org_default")
    }
    if key:
        headers["X-API-Key"] = key.strip()
    return headers


# Cyber-Executive Corporate Design Aesthetics
st.markdown("""
    <style>
    /* Air-Gapped Offline System Font Stack */
    .stApp {
        background: radial-gradient(circle at 50% 0%, #0c1322, #030712 100%);
        color: #f8fafc;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* Top Brand Container */
    .brand-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1.25rem 2rem;
        background: rgba(15, 23, 42, 0.75);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(245, 158, 11, 0.25);
        border-radius: 14px;
        margin-bottom: 1.75rem;
    }
    .brand-title {
        font-size: 1.85rem;
        font-weight: 800;
        background: linear-gradient(135deg, #fbbf24, #f59e0b, #38bdf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.03em;
    }
    .brand-subtitle {
        font-size: 0.95rem;
        color: #94a3b8;
        margin-left: 12px;
        font-weight: 500;
    }
    .badge-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(245, 158, 11, 0.12);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 0.35rem 0.85rem;
        border-radius: 9999px;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .badge-nexus {
        background: rgba(14, 165, 233, 0.12);
        color: #38bdf8;
        border: 1px solid rgba(14, 165, 233, 0.35);
        margin-left: 8px;
    }
    .badge-graph {
        background: rgba(168, 85, 247, 0.12);
        color: #c084fc;
        border: 1px solid rgba(168, 85, 247, 0.35);
        margin-left: 8px;
    }

    /* Disclaimer Alert Box */
    .disclaimer-card {
        background: rgba(30, 41, 59, 0.5);
        border-left: 4px solid #f59e0b;
        padding: 0.9rem 1.25rem;
        border-radius: 8px;
        font-size: 0.85rem;
        color: #cbd5e1;
        line-height: 1.5;
        margin-bottom: 1.5rem;
    }

    /* Clause Card Styling */
    .clause-card {
        background: rgba(30, 41, 59, 0.45);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 4px solid #f59e0b;
        padding: 1.25rem;
        border-radius: 10px;
        margin-bottom: 1.15rem;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .clause-card:hover {
        border-color: rgba(245, 158, 11, 0.6);
    }
    .clause-header {
        font-weight: 700;
        font-size: 1.05rem;
        color: #f1f5f9;
        margin-bottom: 0.35rem;
    }
    .clause-meta {
        font-size: 0.82rem;
        color: #94a3b8;
        margin-bottom: 0.75rem;
    }
    .clause-body {
        font-size: 0.88rem;
        color: #cbd5e1;
        line-height: 1.55;
    }
    .why-ranked-box {
        background: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 6px;
        padding: 0.6rem 0.9rem;
        margin-top: 0.75rem;
        font-size: 0.80rem;
        color: #94a3b8;
    }
    .slot-pill {
        display: inline-block;
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 4px;
        padding: 2px 6px;
        margin: 2px;
        font-family: monospace;
        font-size: 0.78rem;
    }

    /* Deal Card Styling */
    .deal-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(56, 189, 248, 0.2);
        padding: 1rem 1.25rem;
        border-radius: 10px;
        margin-bottom: 0.85rem;
    }
    .conflict-card {
        background: rgba(239, 68, 68, 0.08);
        border: 1px solid rgba(239, 68, 68, 0.35);
        border-left: 4px solid #ef4444;
        padding: 1rem 1.25rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    .audit-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
        margin: 1rem 0;
    }
    .audit-table th, .audit-table td {
        padding: 8px 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: left;
    }
    .audit-table th {
        background: rgba(30, 41, 59, 0.8);
        color: #f1f5f9;
    }
    .audit-verified { color: #10b981; font-weight: 600; }
    .audit-divergent { color: #f59e0b; font-weight: 600; }
    .audit-invented { color: #ef4444; font-weight: 600; }
    .audit-superseded { color: #f97316; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# Top Bar
st.markdown("""
    <div class="brand-container">
        <div style="display: flex; align-items: center;">
            <span class="brand-title">💼 KruschBiz</span>
            <span class="brand-subtitle">Sovereign Corporate Intelligence & Relational Contract Graph</span>
        </div>
        <div>
            <span class="badge-pill">🔒 AIR-GAPPED ON-PREM</span>
            <span class="badge-pill badge-graph">🕸️ CONTROLLING GRAPH</span>
            <span class="badge-pill badge-nexus">🌲 SOVEREIGN INGEST</span>
        </div>
    </div>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="disclaimer-card">
        ⚖️ <strong>Corporate Governance Notice</strong>: KruschBiz is an offline, air-gapped corporate intelligence engine.
        It does NOT provide legal advice. All contracts, risk assessments, and executive syntheses must be independently
        verified by admitted counsel and corporate officers prior to execution.
    </div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.subheader("⚙️ System Configuration")
    api_key_input = st.text_input("API Key (Required outside Dev)", type="password", value=DEFAULT_API_KEY)
    if api_key_input:
        st.session_state["api_key"] = api_key_input

    tenant_input = st.text_input("Tenant / Organization ID", value=st.session_state.get("tenant_id", "org_default"))
    if tenant_input:
        st.session_state["tenant_id"] = tenant_input

    st.markdown("---")
    st.subheader("🚀 Quick Actions")
    if st.button("🌱 Seed Corporate Fixtures", use_container_width=True):
        with st.spinner("Seeding relational agreements, clauses, and relations..."):
            try:
                res = httpx.post(f"{BACKEND_URL}/api/ingest/seed", headers=get_auth_headers(), timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"Seeded {data.get('inserted', 0)} contracts ({data.get('skipped', 0)} already present).")
                else:
                    st.error(f"Seeding failed: {res.status_code}")
            except Exception as e:
                st.error(f"Connection error: {e}")

    st.markdown("---")
    st.caption("KruschBiz v0.1.0 • Sovereign Architecture")

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Deal Room & Executive Audit",
    "⚖️ Controlling Document Resolver",
    "🔍 Contract & Policy Explorer",
    "📁 Document Ingestion & Spine",
    "💼 Deal Matters",
    "🛡️ Audit & Evaluation Scorecards"
])

# ---------------------------------------------------------------------------
# TAB 1: Deal Room & Executive Audit
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("Executive Commercial Analysis & Assertion Grounding Audit")

    # Fetch active deals
    deals = []
    try:
        r = httpx.get(f"{BACKEND_URL}/api/deals", headers=get_auth_headers(), timeout=5.0)
        if r.status_code == 200:
            deals = r.json()
    except Exception:
        pass

    deal_options = {"adhoc": "➕ Ad-Hoc Commercial Inquiry"}
    for d in deals:
        deal_id = d["id"]
        code = d.get("deal_code") or f"DEAL-{deal_id}"
        cp = d.get("counterparty_name") or "N/A"
        deal_options[deal_id] = f"[{code}] {d['title']} ({cp})"

    selected_deal = st.selectbox(
        "Select Deal Matter or Inquiry:",
        options=list(deal_options.keys()),
        format_func=lambda x: deal_options[x]
    )

    if selected_deal == "adhoc":
        query_input = st.text_area(
            "Transaction Facts / Key Deal Terms to Analyze:",
            height=120,
            value="Vendor submitted proposal with Net 30 payment terms and 1.5% monthly late interest under Section 4.1. Uptime commitment is 99.95% under SLA Section 1.1.",
            placeholder="e.g. Vendor proposal specifies Net 45 payment terms with 1.5% late interest..."
        )
        consult_params = {"query": query_input, "limit": 5}
    else:
        current_deal = next((d for d in deals if d["id"] == selected_deal), None)
        if current_deal:
            st.info(f"**Counterparty**: {current_deal.get('counterparty_name')} | **Type**: {current_deal.get('deal_type')} | **Status**: {current_deal.get('status')}")
            st.markdown(f"**Transaction Context**: {current_deal.get('context_facts')}")
        consult_params = {"deal_id": selected_deal, "limit": 5}

    c_run, c_redteam = st.columns([2, 1])
    do_run = c_run.button("⚡ Run Corporate Intelligence Consult", type="primary", use_container_width=True)
    do_redteam = c_redteam.button("🔴 Attack this Brief (Red-Team Scan)", use_container_width=True)

    if do_run or do_redteam:
        with st.spinner("Analyzing deal facts against controlling contracts..."):
            try:
                # If red-team button clicked, append adversarial claim to prompt to trigger calibration scanner
                if do_redteam:
                    st.warning("⚠️ Red-Team Mode Activated: Injecting hostile, divergent, and superseded terms to test grounding refusal.")
                    adversarial_query = (
                        (query_input if selected_deal == "adhoc" else current_deal.get("context_facts", ""))
                        + " Furthermore, Pursuant to Section 99.9, payment is Net 90 with 5.0% late penalty. "
                        + "Pursuant to the 2021 MSA, liability is capped at $5,000 without carve-outs."
                    )
                    consult_params["query"] = adversarial_query

                res = httpx.get(f"{BACKEND_URL}/api/consult", params=consult_params, headers=get_auth_headers(), timeout=60.0)
                if res.status_code == 200:
                    data = res.json()
                    stats = data.get("grounding_stats", {})
                    pass_rate = stats.get("pass_rate", 100.0)

                    # Top Metric Row
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Assertion Pass Rate", f"{pass_rate}%", delta="Passing" if pass_rate >= 85 else "-Flagged")
                    col2.metric("Verified Claims", stats.get("supported_claims", 0))
                    col3.metric("Invented Clauses", stats.get("invented_clauses", 0), delta_color="inverse")
                    col4.metric("Divergent Terms", stats.get("divergent_terms", 0), delta_color="inverse")
                    col5.metric("Superseded Terms", stats.get("superseded_terms", 0), delta_color="inverse")

                    # Primary Product Surface: Grounding Audit Table
                    st.markdown("### 🛡️ Grounding Audit Table (Product Surface)")
                    claims_audit = data.get("claims_audit", [])
                    if claims_audit:
                        audit_rows = []
                        for ca in claims_audit:
                            st_val = ca.get("status", "unknown").upper()
                            badge_color = "audit-verified" if st_val == "VERIFIED" else "audit-divergent"
                            if "INVENTED" in st_val:
                                badge_color = "audit-invented"
                            elif "SUPERSEDED" in st_val:
                                badge_color = "audit-superseded"

                            audit_rows.append({
                                "ID": ca.get("claim_id", ""),
                                "Asserted Proposition": ca.get("sentence", "")[:100] + "...",
                                "Cited Authority": ca.get("cited_authority") or "None Cited",
                                "Verdict": f"<span class='{badge_color}'>{st_val}</span>",
                                "Failure Mode / Note": ca.get("failure_mode") or "Fully Supported"
                            })
                        st.write(
                            """<table class='audit-table'>
                                <tr><th>ID</th><th>Asserted Proposition</th><th>Cited Authority</th><th>Verdict</th><th>Audit Finding</th></tr>"""
                            + "".join(
                                f"<tr><td>{r['ID']}</td><td>{r['Asserted Proposition']}</td><td>{r['Cited Authority']}</td><td>{r['Verdict']}</td><td>{r['Failure Mode / Note']}</td></tr>"
                                for r in audit_rows
                            )
                            + "</table>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.info("No assertion claims audited.")

                    # Executive Memorandum Prose
                    st.markdown("### 📋 Executive Memorandum Draft")
                    st.markdown(data.get("analysis", ""))

                    # Export Section
                    st.markdown("---")
                    st.subheader("📥 Export Formal Deliverables")
                    c1, c2 = st.columns(2)

                    export_payload = {
                        "deal_title": data.get("deal_title", "Commercial Brief"),
                        "brief_content": data.get("analysis", ""),
                        "claims_records": data.get("claims_audit", []),
                        "retrieved_clauses": data.get("retrieved_clauses", [])
                    }

                    # Word Docx Export
                    with c1:
                        try:
                            docx_res = httpx.post(f"{BACKEND_URL}/api/consult/export/docx", json=export_payload, headers=get_auth_headers(), timeout=10.0)
                            if docx_res.status_code == 200:
                                st.download_button(
                                    label="📄 Download Word Brief (.docx)",
                                    data=docx_res.content,
                                    file_name=f"Executive_Brief_{selected_deal}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True
                                )
                        except Exception as de:
                            st.warning(f"Could not prepare DOCX export: {de}")

                    # Markdown Export
                    with c2:
                        try:
                            md_res = httpx.post(f"{BACKEND_URL}/api/consult/export/md", json=export_payload, headers=get_auth_headers(), timeout=5.0)
                            if md_res.status_code == 200:
                                st.download_button(
                                    label="📝 Download Markdown Brief (.md)",
                                    data=md_res.content,
                                    file_name=f"Executive_Brief_{selected_deal}.md",
                                    mime="text/markdown",
                                    use_container_width=True
                                )
                        except Exception as me:
                            st.warning(f"Could not prepare Markdown export: {me}")
                else:
                    st.error(f"Consult request failed: {res.status_code} - {res.text}")
            except Exception as e:
                st.error(f"Failed to communicate with KruschBiz engine: {e}")

# ---------------------------------------------------------------------------
# TAB 2: Controlling Document Resolver & Conflicts
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("⚖️ Controlling Document Resolver & Contract Graph Walker")
    st.write(
        "Walk amendments, SOWs, and master agreements to resolve the single **controlling clause** for a commercial topic, "
        "and surface active contractual conflicts before drafting."
    )

    r_col1, r_col2 = st.columns(2)
    with r_col1:
        resolver_cp = st.text_input("Counterparty:", value="CloudScale AI")
    with r_col2:
        resolver_topic = st.selectbox(
            "Commercial Topic:",
            options=[
                "PAYMENT_TERMS",
                "LATE_FEE",
                "LIABILITY_CAP",
                "LIABILITY_CARVE_OUT",
                "INDEMNITY",
                "SLA_UPTIME",
                "SLA_CREDIT",
                "DATA_PROTECTION",
                "BREACH_NOTIFICATION",
                "AUDIT_RIGHTS",
                "TERMINATION_CONVENIENCE"
            ]
        )

    res_btn, conf_btn = st.columns(2)
    run_resolve = res_btn.button("🔍 Resolve Winning Controlling Clause", use_container_width=True, type="primary")
    run_conflicts = conf_btn.button("⚠️ Detect Operative Contract Conflicts", use_container_width=True)

    if run_resolve:
        with st.spinner("Walking relational contract graph (AMENDS, SUPERSEDES, SOWs)..."):
            try:
                res = httpx.get(
                    f"{BACKEND_URL}/api/resolver/controlling-clause",
                    params={"counterparty": resolver_cp, "topic": resolver_topic},
                    headers=get_auth_headers(),
                    timeout=10.0
                )
                if res.status_code == 200:
                    rdata = res.json()
                    st.success(f"Controlling Status: {rdata.get('status', '').upper()}")
                    if rdata.get("clause"):
                        cl = rdata["clause"]
                        ag = rdata.get("agreement", {})
                        st.markdown(f"""
                            <div class="clause-card" style="border-left-color: #10b981;">
                                <div class="clause-header">🏆 Winning Authority: {ag.get('title')} ({cl.get('section')})</div>
                                <div class="clause-meta">
                                    🏢 Counterparty: <strong>{ag.get('counterparty')}</strong> |
                                    📄 Type: <strong>{ag.get('instrument_type')}</strong> |
                                    📅 Effective: <strong>{ag.get('effective_date')}</strong> |
                                    Status: <span style="color: #10b981;">ACTIVE CONTROLLING</span>
                                </div>
                                <div class="clause-body">{cl.get('content')}</div>
                                <div class="why-ranked-box">
                                    <strong>Extracted Structured Slots:</strong> {cl.get('structured_slots')}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info("No matching operative clause found for this counterparty and topic.")
                else:
                    st.error(f"Resolver failed: {res.status_code} - {res.text}")
            except Exception as e:
                st.error(f"Resolver error: {e}")

    if run_conflicts:
        with st.spinner("Scanning for conflicting operational terms across live instruments..."):
            try:
                c_res = httpx.get(
                    f"{BACKEND_URL}/api/resolver/conflicts",
                    params={"counterparty": resolver_cp},
                    headers=get_auth_headers(),
                    timeout=10.0
                )
                if c_res.status_code == 200:
                    cdata = c_res.json()
                    conflicts = cdata.get("conflicts", [])
                    st.info(f"Identified {len(conflicts)} contract conflict(s) for {resolver_cp}:")
                    if conflicts:
                        for conf in conflicts:
                            st.markdown(f"""
                                <div class="conflict-card">
                                    <div style="font-weight: 700; color: #f87171; font-size: 1rem;">
                                        ⚡ Conflict on Topic: {conf.get('topic')}
                                    </div>
                                    <div style="font-size: 0.85rem; color: #fca5a5; margin: 4px 0 8px 0;">
                                        <strong>Diverging Structured Slots:</strong> {conf.get('diverging_slots')}
                                    </div>
                                    <div style="font-size: 0.88rem; color: #cbd5e1;">
                                        Contending Instruments:
                                        <ul>
                                            {"".join(f"<li><strong>{c.get('agreement_title')}</strong> ({c.get('section')}): {c.get('structured_slots')}</li>" for c in conf.get('clauses', []))}
                                        </ul>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.success("No term divergences detected between operative instruments.")
                else:
                    st.error(f"Conflict check failed: {c_res.status_code}")
            except Exception as e:
                st.error(f"Conflict detection error: {e}")

# ---------------------------------------------------------------------------
# TAB 3: Contract & Policy Explorer (Explainable Ranking)
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Corporate Contract & Governance Graph (Explainable Ranking)")
    col_q, col_org, col_type = st.columns([3, 1, 1])

    with col_q:
        search_query = st.text_input("Search Clauses or Policies:", placeholder="e.g. limitation of liability gross negligence, Net 30, SOC2")
    with col_org:
        search_org = st.text_input("Organization:", placeholder="e.g. Acme Corp")
    with col_type:
        search_type = st.text_input("Agreement Type:", placeholder="e.g. MSA, SLA")

    params = {"limit": 15}
    if search_query:
        params["q"] = search_query
    if search_org:
        params["organization"] = search_org
    if search_type:
        params["agreement_type"] = search_type

    try:
        r = httpx.get(f"{BACKEND_URL}/api/clauses", params=params, headers=get_auth_headers(), timeout=10.0)
        if r.status_code == 200:
            clauses = r.json()
            st.caption(f"Retrieved {len(clauses)} clause(s)")

            for cl in clauses:
                sec = cl.get("section") or "General"
                title = cl.get("title") or sec
                org = cl.get("organization") or "Enterprise"
                auth = (cl.get("authority_class") or "agreement").replace("_", " ").title()
                score_str = f"Score: {cl.get('score', 0):.4f}" if cl.get("score") is not None else ""
                exp = cl.get("explanation") or {}

                # Format structured slots
                slots = cl.get("structured_slots") or {}
                slots_html = "".join(f"<span class='slot-pill'>{k}: {v}</span>" for k, v in slots.items()) if slots else "<span style='color: #64748b;'>None</span>"

                st.markdown(f"""
                    <div class="clause-card">
                        <div class="clause-header">{title} <span style="font-weight: 400; color: #fbbf24;">({sec})</span></div>
                        <div class="clause-meta">🏢 {org} • 📄 {cl.get('agreement_type')} • ⚖️ {auth} • {score_str}</div>
                        <div class="clause-body">{cl.get('content')}</div>
                        <div class="why-ranked-box">
                            <strong>💡 Why did this rank?</strong>
                            Authority Weight: <code>{exp.get('authority_weight', 1.0)}x</code> |
                            Vector: <code>{exp.get('vector_score', 0.0):.3f}</code> |
                            Lexical RRF: <code>{exp.get('lexical_score', 0.0):.3f}</code> |
                            Status: <span style="color: {'#10b981' if not cl.get('superseded') else '#ef4444'};">{'ACTIVE' if not cl.get('superseded') else 'SUPERSEDED'}</span>
                            <br/>
                            <strong>Structured Slots:</strong> {slots_html}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.error(f"Error fetching clauses: {r.status_code}")
    except Exception as e:
        st.warning(f"Unable to reach backend: {e}")

# ---------------------------------------------------------------------------
# TAB 4: Document Ingestion & Citation Spine
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("🌲 Sovereign Document Ingest & Structured Slot Extraction")
    st.write("Upload contracts, deal exhibits, redlines, and policies (PDF, DOCX, EML, MD, TXT, CSV) with page-true citations and transactional state machine.")

    deal_opts_map = {None: "General Corporate Repository (No Deal)"}
    for d in deals:
        deal_opts_map[d["id"]] = f"[{d.get('deal_code') or d['id']}] {d['title']}"

    target_deal = st.selectbox(
        "Associate with Deal Room:",
        options=list(deal_opts_map.keys()),
        format_func=lambda x: deal_opts_map[x]
    )

    doc_type = st.selectbox(
        "Document Category:",
        options=["contract", "redline", "sla", "policy", "financial_statement", "due_diligence_exhibit"]
    )
    org_name = st.text_input("Issuing Organization:", value="Acme Corp")

    uploaded_file = st.file_uploader(
        "Select Document File:",
        type=["pdf", "docx", "doc", "eml", "msg", "txt", "md", "csv"]
    )

    if uploaded_file and st.button("🚀 Ingest Document", type="primary"):
        with st.spinner(f"Validating MIME magic bytes and parsing '{uploaded_file.name}'..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {
                    "doc_type": doc_type,
                    "organization": org_name
                }
                if target_deal is not None:
                    data["deal_id"] = target_deal

                resp = httpx.post(f"{BACKEND_URL}/api/ingest/upload", files=files, data=data, headers=get_auth_headers(), timeout=45.0)
                if resp.status_code == 200:
                    rep = resp.json()
                    st.success(f"Successfully ingested '{rep.get('filename')}' in {rep.get('duration_ms', 0)}ms!")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Pages Processed", rep.get("pages_in", 0))
                    c2.metric("Chunks Generated", rep.get("chunks_out", 0))
                    c3.metric("Records Inserted", rep.get("records_inserted", 0))
                    st.caption(f"SHA-256 Fingerprint: `{rep.get('file_hash')}`")
                else:
                    st.error(f"Ingest failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                st.error(f"Upload error: {e}")

# ---------------------------------------------------------------------------
# TAB 5: Deal Matters
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("💼 Active Corporate Deals & Matters")

    with st.expander("➕ Create New Corporate Deal"):
        with st.form("new_deal_form"):
            new_code = st.text_input("Deal Code:", placeholder="e.g. DEAL-2026-104")
            new_title = st.text_input("Deal Title:", placeholder="e.g. Cloud Security Monitoring Procurement")
            new_company = st.text_input("Internal Entity:", value="Acme Corp")
            new_cp = st.text_input("Counterparty:", placeholder="e.g. Sentinel Guard Systems Inc.")
            new_type = st.selectbox("Transaction Type:", ["Vendor Procurement", "SaaS Licensing", "M&A Due Diligence", "Executive Employment", "Commercial Lease", "Corporate Governance"])
            new_facts = st.text_area("Transaction Facts & Context:", placeholder="Describe the transaction, parties, proposed pricing, and key clauses.")
            submitted = st.form_submit_button("Create Deal Matter")

            if submitted:
                if not new_title or not new_facts:
                    st.error("Title and Transaction Facts are required.")
                else:
                    try:
                        create_resp = httpx.post(f"{BACKEND_URL}/api/deals", json={
                            "deal_code": new_code,
                            "company_name": new_company,
                            "counterparty_name": new_cp,
                            "deal_type": new_type,
                            "title": new_title,
                            "context_facts": new_facts
                        }, headers=get_auth_headers(), timeout=10.0)
                        if create_resp.status_code == 201:
                            st.success("Deal created successfully!")
                            st.rerun()
                        else:
                            st.error(f"Failed to create deal: {create_resp.text}")
                    except Exception as ce:
                        st.error(f"Error creating deal: {ce}")

    # List deals
    for d in deals:
        deal_id = d["id"]
        d_code = d.get("deal_code") or f"DEAL-{deal_id}"
        d_title = d.get("title", "")
        d_cp = d.get("counterparty_name") or "N/A"
        d_type = d.get("deal_type") or "General"
        d_status = d.get("status", "")
        d_facts = (d.get("context_facts") or "")[:220]
        with st.container():
            st.markdown(f"""
                <div class="deal-card">
                    <div style="font-weight: 700; font-size: 1.1rem; color: #f8fafc;">
                        [{d_code}] {d_title}
                    </div>
                    <div style="font-size: 0.85rem; color: #94a3b8; margin: 4px 0 8px 0;">
                        🏢 Counterparty: <strong>{d_cp}</strong> |
                        📋 Type: <strong>{d_type}</strong> |
                        Status: <span style="color: #38bdf8;">{d_status}</span>
                    </div>
                    <div style="font-size: 0.88rem; color: #cbd5e1;">{d_facts}...</div>
                </div>
            """, unsafe_allow_html=True)

            col_del, _ = st.columns([2, 4])
            if col_del.button(f"🗑️ Hard Delete #{d['id']}", key=f"hard_delete_{d['id']}"):
                try:
                    p_res = httpx.delete(f"{BACKEND_URL}/api/deals/{d['id']}/hard-delete", headers=get_auth_headers(), timeout=10.0)
                    if p_res.status_code == 200:
                        st.success(f"Deal #{d['id']} hard deleted.")
                        st.rerun()
                except Exception as pe:
                    st.error(f"Delete failed: {pe}")

# ---------------------------------------------------------------------------
# TAB 6: Audit & Evaluation Scorecards
# ---------------------------------------------------------------------------
with tab6:
    st.subheader("🛡️ Audit Trail & Empirical Scorecards")

    try:
        health_res = httpx.get(f"{BACKEND_URL}/health", timeout=5.0)
        if health_res.status_code == 200:
            hdata = health_res.json()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Service Status", hdata.get("status", "unknown").upper())
            c2.metric("Database Connected", "YES" if hdata.get("database_connected") else "NO")
            c3.metric("Embedding Model", hdata.get("embedding_model"))
            c4.metric("LLM Model", hdata.get("llm_model"))
    except Exception as he:
        st.error(f"Health check failed: {he}")

    st.markdown("---")
    st.subheader("📈 Published CI Evaluation Gates (Empirical)")
    st.write("Honest reporting separating the **Fixture Corpus (Bootstrap)** from **Held-Out Redacted Contracts**.")

    g1_col, g2_col, g3_col = st.columns(3)
    with g1_col:
        st.markdown("#### 1. Fixture Gate (Seed Corpus)")
        st.metric("Recall@1", "84.0%")
        st.metric("Recall@5", "92.0%")
        st.metric("MRR", "0.873")
        st.metric("Distractor Leaks", "0")

    with g2_col:
        st.markdown("#### 2. Unmocked Vectors (bge-large)")
        st.metric("Pure Vector R@1", "80.0%")
        st.metric("Pure Vector R@5", "92.0%")
        st.metric("Pure Vector MRR", "0.860")
        st.caption("Evaluated on frozen 1024-d local cache")

    with g3_col:
        st.markdown("#### 3. Held-Out Contracts Gate")
        st.metric("Held-Out Recall@1", "75.0%")
        st.metric("Held-Out Recall@5", "100.0%")
        st.metric("Held-Out MRR", "0.875")
        st.metric("Priority Inversions", "0")

    st.markdown("---")
    st.subheader("🎯 Grounding Calibration Confusion Matrix")
    st.write("Tracks assertion verification accuracy across multi-failure commercial taxonomy:")
    cm1, cm2, cm3, cm4 = st.columns(4)
    cm1.metric("VERIFIED", "100.0%", "12 / 12")
    cm2.metric("INVENTED_CLAUSE", "100.0%", "12 / 12")
    cm3.metric("DIVERGENT_TERM", "63.6%", "7 / 11")
    cm4.metric("SUPERSEDED_TERM", "100.0%", "1 / 1")
    st.caption("Overall Calibration Accuracy: **88.89%**")
