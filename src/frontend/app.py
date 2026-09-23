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
    """Return authorization headers with configured API key if available."""
    key = st.session_state.get("api_key", DEFAULT_API_KEY)
    headers = {}
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

    /* Deal Card Styling */
    .deal-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(56, 189, 248, 0.2);
        padding: 1rem 1.25rem;
        border-radius: 10px;
        margin-bottom: 0.85rem;
    }
    </style>
""", unsafe_allow_html=True)

# Top Bar
st.markdown("""
    <div class="brand-container">
        <div style="display: flex; align-items: center;">
            <span class="brand-title">💼 KruschBiz</span>
            <span class="brand-subtitle">Sovereign Corporate Intelligence & Contract Graph</span>
        </div>
        <div>
            <span class="badge-pill">🔒 AIR-GAPPED ON-PREM</span>
            <span class="badge-pill badge-nexus">🌲 KRUSCHNEXUS SPINE</span>
        </div>
    </div>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="disclaimer-card">
        ⚖️ <strong>Corporate Governance Notice</strong>: KruschBiz is an offline, air-gapped corporate research prototype.
        It does NOT provide legal advice. All contracts, risk assessments, and executive syntheses must be independently
        verified by admitted counsel and corporate officers prior to execution.
    </div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.subheader("⚙️ System Configuration")
    api_key_input = st.text_input("API Key (Optional)", type="password", value=DEFAULT_API_KEY)
    if api_key_input:
        st.session_state["api_key"] = api_key_input

    st.markdown("---")
    st.subheader("🚀 Quick Actions")
    if st.button("🌱 Seed Corporate Fixtures", use_container_width=True):
        with st.spinner("Seeding demo contracts, MSAs, and SLAs..."):
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
    st.caption("KruschBiz v0.3.0 • Slalom AI Architecture")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Executive Deal Analysis",
    "🔍 Contract & Policy Explorer",
    "📁 Deal Room & Ingest (KruschNexus)",
    "💼 Deal Portfolio",
    "🛡️ Audit & System Diagnostics"
])

# ---------------------------------------------------------------------------
# TAB 1: Executive Deal Analysis
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("Executive Commercial Analysis & Risk Grounding")

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
            placeholder="e.g. Vendor proposal specifies Net 45 payment terms with 1.5% late interest. SLA claims 99.9% uptime with 10% credit. Vendor requests limitation of liability cap at $50,000."
        )
        consult_params = {"query": query_input, "limit": 5}
    else:
        current_deal = next((d for d in deals if d["id"] == selected_deal), None)
        if current_deal:
            st.info(f"**Counterparty**: {current_deal.get('counterparty_name')} | **Type**: {current_deal.get('deal_type')} | **Status**: {current_deal.get('status')}")
            st.markdown(f"**Transaction Context**: {current_deal.get('context_facts')}")
        consult_params = {"deal_id": selected_deal, "limit": 5}

    if st.button("⚡ Run Corporate Intelligence Consult", type="primary"):
        with st.spinner("Retrieving governing contracts & executing assertion-level grounding scan..."):
            try:
                res = httpx.get(f"{BACKEND_URL}/api/consult", params=consult_params, headers=get_auth_headers(), timeout=60.0)
                if res.status_code == 200:
                    data = res.json()
                    stats = data.get("grounding_stats", {})
                    pass_rate = stats.get("pass_rate", 100.0)

                    # Top Metric Row
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Assertion Pass Rate", f"{pass_rate}%", delta="Passing" if pass_rate >= 90 else "-Regressed")
                    col2.metric("Verified Claims", stats.get("supported_claims", 0))
                    col3.metric("Invented Clauses", stats.get("invented_clauses", 0), delta_color="inverse")
                    col4.metric("Superseded Terms", stats.get("superseded_terms", 0), delta_color="inverse")

                    # Brief Display
                    st.markdown("### 📋 Executive Memorandum Draft")
                    st.markdown(data.get("analysis", ""))

                    # Export Buttons
                    st.markdown("---")
                    st.subheader("📥 Export Formal Deliverables")
                    c1, c2 = st.columns(2)

                    export_payload = {
                        "deal_title": data.get("deal_title", "Commercial Brief"),
                        "brief_content": data.get("analysis", ""),
                        "claims_audit": data.get("claims_audit", []),
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
                                    data=md_res.json().get("markdown", ""),
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
# TAB 2: Contract & Policy Explorer
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Corporate Contract & Governance Graph")
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
                score_str = f"Score: {cl.get('rrf_score', 0):.4f}" if cl.get("rrf_score") is not None else ""

                st.markdown(f"""
                    <div class="clause-card">
                        <div class="clause-header">{title} <span style="font-weight: 400; color: #fbbf24;">({sec})</span></div>
                        <div class="clause-meta">🏢 {org} • 📄 {cl.get('agreement_type')} • ⚖️ {auth} • {score_str}</div>
                        <div class="clause-body">{cl.get('content')}</div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.error(f"Error fetching clauses: {r.status_code}")
    except Exception as e:
        st.warning(f"Unable to reach backend: {e}")

# ---------------------------------------------------------------------------
# TAB 3: Deal Room & Document Ingestion (KruschNexus)
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("🌲 Sovereign KruschNexus Document Ingest")
    st.write("Upload contracts, deal exhibits, redlines, and policies (PDF, DOCX, EML, MD, TXT, CSV) with page-true citations.")

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

    if uploaded_file and st.button("🚀 Ingest Document via KruschNexus", type="primary"):
        with st.spinner(f"Parsing '{uploaded_file.name}' with KruschNexus citation spine..."):
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
# TAB 4: Deal Portfolio
# ---------------------------------------------------------------------------
with tab4:
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

            col_del, _ = st.columns([1, 5])
            if col_del.button(f"🗑️ Purge #{d['id']}", key=f"purge_{d['id']}"):
                try:
                    p_res = httpx.delete(f"{BACKEND_URL}/api/deals/{d['id']}/purge", headers=get_auth_headers(), timeout=10.0)
                    if p_res.status_code == 200:
                        st.success(f"Deal #{d['id']} purged.")
                        st.rerun()
                except Exception as pe:
                    st.error(f"Purge failed: {pe}")

# ---------------------------------------------------------------------------
# TAB 5: Audit Trail & System Diagnostics
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("🛡️ Audit Trail & Engine Diagnostics")

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
