import json
import os
from datetime import datetime, timezone
import httpx
import streamlit as st

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


def format_slot_display(slots: dict) -> list[str]:
    """Format structured slots into human-readable provenance strings."""
    if not isinstance(slots, dict):
        return []
    pills = []
    for k, v in slots.items():
        if isinstance(v, dict) and "value" in v:
            val = v.get("value")
            unit = v.get("unit") or ""
            span = v.get("raw_span")
            start = v.get("char_start")
            end = v.get("char_end")
            conf = v.get("confidence")
            display = f"{k}: {val} {unit}".strip()
            if span:
                display += f' • span: "{span}"'
            if start is not None and end is not None:
                display += f" [{start}..{end}]"
            if conf is not None:
                display += f" ({int(conf * 100)}%)"
            pills.append(display)
        else:
            pills.append(f"{k}: {v}")
    return pills


# Cyber-Executive Corporate Design Aesthetics
st.markdown("""
    <style>
    /* ── Frontend MCP Design System Tokens (Refactoring UI & WCAG AAA) ── */
    :root {
        --bg-canvas: #070b14;
        --bg-surface: rgba(15, 23, 42, 0.75);
        --bg-surface-elevated: rgba(30, 41, 59, 0.7);
        --border-subtle: rgba(255, 255, 255, 0.08);
        --border-accent-gold: rgba(245, 158, 11, 0.3);
        --color-gold: #f59e0b;
        --color-gold-light: #fbbf24;
        --color-gold-glow: rgba(245, 158, 11, 0.35);
        --color-emerald: #10b981;
        --color-emerald-light: #34d399;
        --color-sky: #0ea5e9;
        --color-sky-light: #38bdf8;
        --color-crimson: #ef4444;
        --color-crimson-light: #f87171;
        --color-purple: #8b5cf6;
        --text-primary: #f8fafc;
        --text-secondary: #cbd5e1;
        --text-muted: #94a3b8;
        --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        --radius-sm: 6px;
        --radius-md: 10px;
        --radius-lg: 14px;
        --radius-full: 9999px;
        --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* Air-Gapped Offline System Font Stack & Canvas */
    .stApp {
        background: radial-gradient(circle at 50% -12%, #172554 0%, #090d16 40%, #030712 100%);
        color: var(--text-primary);
        font-family: var(--font-stack);
    }

    /* Top Brand Container */
    .brand-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1.25rem 2rem;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.65) 100%);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(245, 158, 11, 0.28);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.08);
        border-radius: var(--radius-lg);
        margin-bottom: 1.25rem;
    }
    .brand-title {
        font-size: 1.95rem;
        font-weight: 800;
        background: linear-gradient(135deg, #fef08a 0%, #fbbf24 35%, #f59e0b 70%, #38bdf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.03em;
    }
    .brand-subtitle {
        font-size: 0.95rem;
        color: var(--text-muted);
        margin-left: 14px;
        font-weight: 500;
    }
    .badge-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(245, 158, 11, 0.14);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 0.35rem 0.85rem;
        border-radius: var(--radius-full);
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.15);
    }
    .badge-nexus {
        background: rgba(14, 165, 233, 0.14);
        color: #38bdf8;
        border: 1px solid rgba(14, 165, 233, 0.35);
        margin-left: 8px;
        box-shadow: 0 2px 8px rgba(14, 165, 233, 0.15);
    }
    .badge-graph {
        background: rgba(168, 85, 247, 0.14);
        color: #c084fc;
        border: 1px solid rgba(168, 85, 247, 0.35);
        margin-left: 8px;
        box-shadow: 0 2px 8px rgba(168, 85, 247, 0.15);
    }

    /* Disclaimer Alert Box */
    .disclaimer-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 4px solid #f59e0b;
        padding: 0.95rem 1.35rem;
        border-radius: var(--radius-md);
        font-size: 0.86rem;
        color: var(--text-secondary);
        line-height: 1.55;
        margin-bottom: 1.35rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }

    /* ── Streamlit Native UI Components Styling ── */

    /* Tabs Styling - Modern Streamlit React-Aria High Contrast Selectors */
    div[role="tablist"],
    .stTabs [data-baseweb="tab-list"],
    div[data-testid="stTabList"] {
        background: rgba(15, 23, 42, 0.92) !important;
        backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 12px !important;
        padding: 8px !important;
        gap: 8px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45) !important;
        margin-bottom: 1.5rem !important;
    }

    /* Individual Tab Buttons (Inactive) */
    div[data-testid="stTab"],
    div[role="tab"],
    .stTabs [data-baseweb="tab"] {
        background: rgba(30, 41, 59, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 8px !important;
        padding: 10px 22px !important;
        transition: all var(--transition-fast) !important;
        cursor: pointer !important;
        opacity: 1 !important;
    }

    /* Tab Text - PURE CRISP HIGH-CONTRAST SILVER-WHITE */
    div[data-testid="stTab"] p,
    div[data-testid="stTab"] span,
    div[data-testid="stTab"] div,
    div[role="tab"] p,
    div[role="tab"] span,
    div[role="tab"] div,
    div[role="tab"] [data-testid="stMarkdownContainer"] *,
    .stTabs [data-baseweb="tab"] p,
    .stTabs [data-baseweb="tab"] span,
    .stTabs [data-baseweb="tab"] div,
    .stTabs [data-baseweb="tab"] [data-testid="stMarkdownContainer"] * {
        color: #f8fafc !important; /* Pure crisp bright silver-white for maximum legibility */
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        opacity: 1 !important;
    }

    /* Tab Hover State */
    div[data-testid="stTab"]:hover,
    div[role="tab"]:hover,
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(51, 65, 85, 0.95) !important;
        border-color: rgba(245, 158, 11, 0.6) !important;
    }
    div[data-testid="stTab"]:hover p,
    div[data-testid="stTab"]:hover span,
    div[role="tab"]:hover p,
    div[role="tab"]:hover span,
    .stTabs [data-baseweb="tab"]:hover p,
    .stTabs [data-baseweb="tab"]:hover span {
        color: #ffffff !important;
    }

    /* Active Selected Tab - VIBRANT EXECUTIVE GOLD */
    div[data-testid="stTab"][aria-selected="true"],
    div[data-testid="stTab"][data-selected="true"],
    div[role="tab"][aria-selected="true"],
    div[role="tab"][data-selected="true"],
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.28) 0%, rgba(217, 119, 6, 0.18) 100%) !important;
        border: 1px solid rgba(245, 158, 11, 0.85) !important;
        border-bottom: 3px solid #f59e0b !important;
        box-shadow: 0 4px 18px rgba(245, 158, 11, 0.35) !important;
    }

    div[data-testid="stTab"][aria-selected="true"] p,
    div[data-testid="stTab"][aria-selected="true"] span,
    div[data-testid="stTab"][aria-selected="true"] div,
    div[role="tab"][aria-selected="true"] p,
    div[role="tab"][aria-selected="true"] span,
    div[role="tab"][aria-selected="true"] div,
    div[role="tab"][aria-selected="true"] [data-testid="stMarkdownContainer"] *,
    .stTabs [data-baseweb="tab"][aria-selected="true"] p,
    .stTabs [data-baseweb="tab"][aria-selected="true"] span,
    .stTabs [data-baseweb="tab"][aria-selected="true"] div,
    .stTabs [data-baseweb="tab"][aria-selected="true"] [data-testid="stMarkdownContainer"] * {
        color: #fbbf24 !important; /* Vibrant high-contrast executive gold */
        font-weight: 800 !important;
    }

    /* Selection Indicator Bar Override */
    div.react-aria-SelectionIndicator {
        background-color: #f59e0b !important;
        height: 3px !important;
        border-radius: 2px !important;
    }

    .stTabs [data-baseweb="tab-highlight"] {
        background-color: transparent !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }

    /* High-Contrast Universal Typography Overrides */
    .stCaption, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
        color: #cbd5e1 !important; /* Clearly readable silver-gray */
        font-size: 0.88rem !important;
        font-weight: 500 !important;
    }
    label, [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * {
        color: #f8fafc !important; /* Crisp high-contrast white */
        font-weight: 600 !important;
        font-size: 0.90rem !important;
    }

    /* Button Hierarchy (Refactoring UI Principle) */
    div.stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        padding: 0.55rem 1.25rem !important;
        min-height: 42px !important;
        transition: all var(--transition-fast) !important;
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: #050811 !important;
        font-weight: 700 !important;
        border: 1px solid rgba(254, 240, 138, 0.45) !important;
        box-shadow: 0 4px 14px rgba(245, 158, 11, 0.3) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 22px rgba(245, 158, 11, 0.5) !important;
        background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%) !important;
    }
    div.stButton > button[kind="primary"]:active {
        transform: translateY(0px) !important;
    }
    div.stButton > button[kind="secondary"],
    div.stButton > button:not([kind="primary"]) {
        background: rgba(30, 41, 59, 0.6) !important;
        color: var(--text-secondary) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25) !important;
    }
    div.stButton > button[kind="secondary"]:hover,
    div.stButton > button:not([kind="primary"]):hover {
        border-color: rgba(245, 158, 11, 0.5) !important;
        color: #fbbf24 !important;
        background: rgba(30, 41, 59, 0.9) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35) !important;
    }

    /* Polished Metric Cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.75) 0%, rgba(30, 41, 59, 0.45) 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-top: 3px solid #f59e0b !important;
        border-radius: var(--radius-md) !important;
        padding: 0.95rem 1.25rem !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28) !important;
        backdrop-filter: blur(10px) !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        color: var(--text-muted) !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.65rem !important;
        font-weight: 800 !important;
        color: var(--text-primary) !important;
    }

    /* Form Inputs and Select Boxes */
    div[data-baseweb="select"] > div,
    input.stTextInput,
    div.stTextInput > div > div > input,
    textarea.stTextArea,
    div.stTextArea > div > div > textarea {
        background-color: rgba(15, 23, 42, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 8px !important;
        color: #f1f5f9 !important;
        transition: border-color var(--transition-fast), box-shadow var(--transition-fast) !important;
    }
    div[data-baseweb="select"] > div:focus-within,
    div.stTextInput > div > div > input:focus,
    div.stTextArea > div > div > textarea:focus {
        border-color: #f59e0b !important;
        box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.25) !important;
    }

    /* ── Specific Domain Cards ── */

    /* Clause Card Styling */
    .clause-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.65) 100%);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 4px solid #f59e0b;
        padding: 1.25rem;
        border-radius: var(--radius-md);
        margin-bottom: 1.15rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28);
        transition: transform var(--transition-fast), border-color var(--transition-fast);
    }
    .clause-card:hover {
        border-color: rgba(245, 158, 11, 0.6);
        transform: translateY(-1px);
    }
    .clause-header {
        font-weight: 700;
        font-size: 1.05rem;
        color: #f1f5f9;
        margin-bottom: 0.35rem;
    }
    .clause-meta {
        font-size: 0.82rem;
        color: var(--text-muted);
        margin-bottom: 0.75rem;
    }
    .clause-body {
        font-size: 0.88rem;
        color: var(--text-secondary);
        line-height: 1.55;
    }
    .why-ranked-box {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 6px;
        padding: 0.65rem 0.95rem;
        margin-top: 0.75rem;
        font-size: 0.80rem;
        color: var(--text-muted);
    }

    /* Edge Card Styling */
    .edge-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.65) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(245, 158, 11, 0.35);
        border-left: 4px solid #f59e0b;
        border-radius: var(--radius-md);
        padding: 1.15rem 1.35rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        transition: transform var(--transition-fast), box-shadow var(--transition-fast);
    }
    .edge-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    }
    .edge-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-weight: 700;
        font-size: 0.95rem;
        color: var(--text-primary);
        margin-bottom: 0.4rem;
    }
    .edge-excerpt {
        background: rgba(15, 23, 42, 0.75);
        border-left: 3px solid #fbbf24;
        padding: 0.55rem 0.85rem;
        border-radius: 6px;
        font-size: 0.85rem;
        color: #e2e8f0;
        font-style: italic;
        margin: 0.5rem 0;
    }

    /* Split-Pane Box in Review Queue */
    .split-pane-box {
        background: rgba(15, 23, 42, 0.75);
        padding: 1rem 1.25rem;
        border-radius: var(--radius-md);
        border: 1px solid rgba(148, 163, 184, 0.2);
        min-height: 190px;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }

    /* Pills & Slots */
    .slot-pill {
        display: inline-block;
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 4px;
        padding: 2px 7px;
        margin: 2px;
        font-family: monospace;
        font-size: 0.78rem;
    }
    .tag-pill {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: rgba(56, 189, 248, 0.12);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.35);
        padding: 0.15rem 0.55rem;
        border-radius: var(--radius-full);
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 4px;
        margin-bottom: 4px;
    }
    .topic-pill {
        display: inline-flex;
        align-items: center;
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        text-transform: uppercase;
    }

    /* Conflict & Evidence Cards */
    .conflict-card {
        background: linear-gradient(145deg, rgba(239, 68, 68, 0.08) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid rgba(239, 68, 68, 0.35);
        border-left: 4px solid #ef4444;
        padding: 1.15rem 1.35rem;
        border-radius: var(--radius-md);
        margin-bottom: 1rem;
        box-shadow: 0 4px 16px rgba(239, 68, 68, 0.15);
    }
    .evidence-card {
        background: rgba(30, 41, 59, 0.45);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 4px solid #38bdf8;
        padding: 1.15rem;
        border-radius: var(--radius-md);
        margin-bottom: 1.15rem;
    }
    .deal-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(56, 189, 248, 0.2);
        padding: 1rem 1.25rem;
        border-radius: var(--radius-md);
        margin-bottom: 0.85rem;
    }

    /* Grounding Audit Table */
    .audit-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 0.86rem;
        margin: 1.25rem 0;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }
    .audit-table th {
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%);
        color: #f8fafc;
        font-weight: 700;
        padding: 10px 14px;
        text-align: left;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
    }
    .audit-table td {
        padding: 10px 14px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        background: rgba(15, 23, 42, 0.5);
        color: #cbd5e1;
    }
    .audit-table tr:hover td {
        background: rgba(30, 41, 59, 0.65);
    }
    .audit-verified { color: #10b981; font-weight: 700; }
    .audit-divergent { color: #f59e0b; font-weight: 700; }
    .audit-invented { color: #ef4444; font-weight: 700; }
    .audit-superseded { color: #f97316; font-weight: 700; }

    /* Uncertainty Warning Banner */
    .uncertainty-banner {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.14) 0%, rgba(217, 119, 6, 0.08) 100%);
        border: 2px solid rgba(245, 158, 11, 0.6);
        border-radius: var(--radius-md);
        padding: 1.15rem 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 0 24px rgba(245, 158, 11, 0.18);
    }

    /* Compliance Card Styling */
    .compliance-card {
        background: rgba(15, 23, 42, 0.65);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: var(--radius-md);
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }
    .compliance-card-violation {
        border-left: 5px solid #ef4444;
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(15, 23, 42, 0.7) 100%);
    }
    .compliance-card-aligned {
        border-left: 5px solid #10b981;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(15, 23, 42, 0.7) 100%);
    }
    .compliance-card-generous {
        border-left: 5px solid #06b6d4;
        background: linear-gradient(135deg, rgba(6, 182, 212, 0.08) 0%, rgba(15, 23, 42, 0.7) 100%);
    }
    .compliance-card-gap {
        border-left: 5px solid #64748b;
        background: linear-gradient(135deg, rgba(100, 116, 139, 0.08) 0%, rgba(15, 23, 42, 0.7) 100%);
    }
    .badge-void {
        background: rgba(239, 68, 68, 0.15);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
        padding: 0.25rem 0.65rem;
        border-radius: var(--radius-full);
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-enforceable {
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.4);
        padding: 0.25rem 0.65rem;
        border-radius: var(--radius-full);
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-generous {
        background: rgba(6, 182, 212, 0.15);
        color: #22d3ee;
        border: 1px solid rgba(6, 182, 212, 0.4);
        padding: 0.25rem 0.65rem;
        border-radius: var(--radius-full);
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-gap {
        background: rgba(100, 116, 139, 0.15);
        color: #94a3b8;
        border: 1px solid rgba(100, 116, 139, 0.4);
        padding: 0.25rem 0.65rem;
        border-radius: var(--radius-full);
        font-weight: 700;
        font-size: 0.78rem;
    }
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
    st.caption("KruschBiz v0.1.0-alpha.1 • Sovereign Corporate Intelligence Engine")

# Fetch common entities
deals = []
try:
    r_deals = httpx.get(f"{BACKEND_URL}/api/deals", headers=get_auth_headers(), timeout=5.0)
    if r_deals.status_code == 200:
        deals = r_deals.json()
except Exception:
    pass

agreements_meta = []
known_counterparties = ["CloudScale AI", "Sentinel Guard Systems Inc.", "Datastream Logistics"]
try:
    r_ag = httpx.get(f"{BACKEND_URL}/api/agreements", headers=get_auth_headers(), timeout=5.0)
    if r_ag.status_code == 200:
        agreements_meta = r_ag.json()
        for a in agreements_meta:
            cp = a.get("counterparty")
            if cp and cp not in known_counterparties:
                known_counterparties.append(cp)
except Exception:
    pass


# 4-Tab Core Precedence & Controlling Architecture
tab1, tab2, tab3, tab4 = st.tabs([
    "🏛️ The Deal Room",
    "🔗 Relation Review Queue & Precedence Graph",
    "🌲 Sovereign Ingest & Deep Extraction",
    "🛡️ Adversarial Multi-Document Scorecard"
])


# ===========================================================================
# TAB 1: 🏛️ The Deal Room (The Primary Executive Workflow)
# ===========================================================================
with tab1:
    st.subheader("🏛️ The Deal Room: Controlling Terms, Human Review & Assertion Grounding")
    st.caption("Autonomous contract graph intelligence: Ground executive assertions, resolve operative terms, and audit proposed relations.")

    # 1. Counterparty Selector + As-Of Date Picker (UTC Date-Only)
    c_cp, c_date = st.columns([2, 1])
    with c_cp:
        deal_room_cp = st.selectbox(
            "Select Counterparty / Vendor:",
            options=known_counterparties,
            index=0 if "CloudScale AI" in known_counterparties else 0,
            key="deal_room_cp"
        )
    with c_date:
        deal_room_as_of = st.date_input(
            "As-Of Evaluation Date (UTC):",
            value=datetime.now(timezone.utc).date(),
            help="Temporal evaluation boundary. Clauses and amendments effective after this date are ignored.",
            key="deal_room_as_of"
        )
    as_of_str = deal_room_as_of.isoformat()

    st.markdown("---")

    # 2. Controlling Clause Uncertainty Banner
    try:
        rel_resp = httpx.get(
            f"{BACKEND_URL}/api/relations",
            params={"status": "proposed"},
            headers=get_auth_headers(),
            timeout=5.0
        )
        if rel_resp.status_code == 200:
            proposed_edges = rel_resp.json()
            if proposed_edges:
                p_cnt = len(proposed_edges)
                st.markdown(f"""
                    <div class="uncertainty-banner">
                        <div style="font-weight: 800; font-size: 1.05rem; color: #fbbf24; display: flex; align-items: center; gap: 8px;">
                            <span>⚠️</span> <span>CONTROLLING CLAUSE UNCERTAIN; {p_cnt} proposed relation link(s) pending human review.</span>
                        </div>
                        <div style="font-size: 0.88rem; color: #e2e8f0; margin-top: 6px; line-height: 1.5;">
                            Precedence traversal strictly enforces zero silent assumptions: unconfirmed <code>AMENDS</code>, <code>SUPERSEDES</code>, or <code>INCORPORATES</code> links are excluded from the controlling DAG walk until approved.
                            Open <strong>Tab 2 (Relation Review Queue & Precedence Graph)</strong> to accept, reject, or edit pending links.
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.caption("✅ All relation edges confirmed. Precedence graph is deterministic.")
    except Exception:
        pass

    st.markdown("---")

    # 3. Controlling Terms Cards per Topic
    st.markdown("### 📋 Operative Controlling Terms per Topic")
    st.write(f"Controlling provisions for **{deal_room_cp}** as of **{as_of_str}**:")

    topics_to_evaluate = [
        "PAYMENT_TERMS",
        "LATE_FEE",
        "LIABILITY_CAP",
        "INDEMNITY",
        "SLA_UPTIME",
        "SLA_CREDIT",
        "DATA_PROTECTION",
        "BREACH_NOTIFICATION",
        "TERMINATION_CONVENIENCE",
        "GOVERNING_LAW"
    ]

    col_t1, col_t2 = st.columns(2)
    for idx, top in enumerate(topics_to_evaluate):
        target_col = col_t1 if idx % 2 == 0 else col_t2
        with target_col:
            try:
                res_cl = httpx.get(
                    f"{BACKEND_URL}/api/resolver/controlling-clause",
                    params={"counterparty": deal_room_cp, "topic": top, "as_of_date": as_of_str},
                    headers=get_auth_headers(),
                    timeout=5.0
                )
                if res_cl.status_code == 200:
                    cldata = res_cl.json()
                    st_val = cldata.get("status", "unknown")
                    cl_obj = cldata.get("controlling_clause") or cldata.get("clause")
                    conf = cldata.get("confidence", 0.0)
                    trail = cldata.get("amendment_trail", [])

                    if st_val == "resolved" and cl_obj:
                        slots = cl_obj.get("structured_slots") or {}
                        slot_pills = format_slot_display(slots)
                        slots_html = "".join(f"<span class='slot-pill'>{s}</span>" for s in slot_pills) if slot_pills else "<span style='color: #94a3b8; font-size: 0.78rem;'>No structured slots</span>"

                        trail_html = ""
                        if trail:
                            trail_steps = " ➔ ".join(f"{h.get('from_agreement_title', 'Agreement')} (§{h.get('from_section')}) ➔ <strong>{h.get('to_agreement_title')}</strong> (§{h.get('to_section')})" for h in trail)
                            trail_html = f"<div style='font-size: 0.78rem; color: #a78bfa; margin-top: 4px;'><strong>Amendment Walk:</strong> {trail_steps}</div>"

                        st.markdown(f"""
                            <div class="clause-card" style="border-left-color: #10b981; padding: 0.9rem;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                    <div class="topic-pill">{top}</div>
                                    <span style="color: #10b981; font-weight: 700; font-size: 0.8rem;">🏆 CONTROLLING ({int(conf*100)}%)</span>
                                </div>
                                <div style="font-weight: 600; color: #f1f5f9; font-size: 0.92rem; margin: 4px 0;">
                                    📄 {cl_obj.get('agreement_title')} <span style="color: #94a3b8; font-weight: 400;">(§ {cl_obj.get('section', 'N/A')})</span>
                                </div>
                                <div style="margin: 4px 0;">{slots_html}</div>
                                {trail_html}
                            </div>
                        """, unsafe_allow_html=True)
                    elif st_val == "ambiguous":
                        st.markdown(f"""
                            <div class="clause-card" style="border-left-color: #ef4444; padding: 0.9rem;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                    <div class="topic-pill">{top}</div>
                                    <span style="color: #ef4444; font-weight: 700; font-size: 0.8rem;">⚡ AMBIGUOUS (0.0 CONFIDENCE)</span>
                                </div>
                                <div style="font-size: 0.82rem; color: #fca5a5; margin-top: 4px;">
                                    {cldata.get('resolution_rationale')}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                            <div class="clause-card" style="border-left-color: #64748b; padding: 0.9rem; opacity: 0.75;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div class="topic-pill" style="color: #94a3b8; border-color: #64748b;">{top}</div>
                                    <span style="color: #94a3b8; font-size: 0.8rem;">⚪ NOT SPECIFIED</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
            except Exception:
                pass

    st.markdown("---")

    # 4. Conflict & Ambiguity Cards
    try:
        conf_resp = httpx.get(
            f"{BACKEND_URL}/api/resolver/conflicts",
            params={"counterparty": deal_room_cp, "as_of_date": as_of_str},
            headers=get_auth_headers(),
            timeout=5.0
        )
        if conf_resp.status_code == 200:
            cdata = conf_resp.json()
            conflicts = cdata.get("conflicts", [])
            if conflicts:
                st.markdown("### ⚠️ Active Operative Conflicts Across Instruments")
                st.warning(f"Identified {len(conflicts)} term conflict(s) for {deal_room_cp} requiring resolution or amendment:")
                for conf in conflicts:
                    st.markdown(f"""
                        <div class="conflict-card">
                            <div style="font-weight: 700; color: #f87171; font-size: 0.95rem;">
                                ⚡ Topic Divergence: {conf.get('topic')} (Confidence: 0.0)
                            </div>
                            <div style="font-size: 0.84rem; color: #fca5a5; margin: 4px 0 6px 0;">
                                <strong>Diverging Structured Slots:</strong> {conf.get('diverging_slots')}
                            </div>
                            <div style="font-size: 0.84rem; color: #cbd5e1;">
                                Contending Instruments:
                                <ul>
                                    {"".join(f"<li><strong>{c.get('agreement_title')}</strong> ({c.get('section')}): {c.get('structured_slots')}</li>" for c in conf.get('clauses', []))}
                                </ul>
                            </div>
                            <div style="font-size: 0.78rem; color: #94a3b8; font-style: italic; margin-top: 4px;">
                                Strict Invariant: No governing AMENDS or order-of-precedence edge exists. The engine refuses to extrapolate a winner.
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.success(f"✅ Zero active term conflicts detected for {deal_room_cp} as of {as_of_str}.")
    except Exception:
        pass

    st.markdown("---")

    # 5. Grounded Commercial Brief & Assertion Audit
    st.markdown("### 🛡️ Grounded Commercial Brief & Assertion Audit")
    st.write("Submit deal propositions to audit every asserted sentence against the controlling contract graph:")

    # Deal Selector or Ad-Hoc
    deal_options = {"adhoc": f"➕ Ad-Hoc Inquiry ({deal_room_cp})"}
    for d in deals:
        deal_id = d["id"]
        code = d.get("deal_code") or f"DEAL-{deal_id}"
        cp = d.get("counterparty_name") or "N/A"
        deal_options[deal_id] = f"[{code}] {d['title']} ({cp})"

    selected_deal = st.selectbox(
        "Link to Deal Matter (Optional):",
        options=list(deal_options.keys()),
        format_func=lambda x: deal_options[x]
    )

    if selected_deal == "adhoc":
        query_input = st.text_area(
            "Transaction Facts / Key Deal Terms to Analyze:",
            height=120,
            value=f"Vendor ({deal_room_cp}) submitted proposal with Net 30 payment terms and 1.5% monthly late interest under Section 4.1. Uptime commitment is 99.95% under SLA Section 1.1.",
            placeholder="e.g. Vendor proposal specifies Net 45 payment terms with 1.5% late interest..."
        )
        consult_params = {"query": query_input, "limit": 5}
    else:
        current_deal = next((d for d in deals if d["id"] == selected_deal), None)
        if current_deal:
            st.info(f"**Counterparty**: {current_deal.get('counterparty_name')} | **Type**: {current_deal.get('deal_type')} | **Status**: {current_deal.get('status')}")
            st.markdown(f"**Context Facts**: {current_deal.get('context_facts')}")
        consult_params = {"deal_id": selected_deal, "limit": 5}

    c_run, c_redteam = st.columns([2, 1])
    do_run = c_run.button("⚡ Run Grounded Brief Consult", type="primary", use_container_width=True)
    do_redteam = c_redteam.button("🔴 Attack with Red-Team Scan", use_container_width=True)

    if do_run or do_redteam:
        with st.spinner("Auditing assertions against controlling contract DAG..."):
            try:
                if do_redteam:
                    st.warning("⚠️ Red-Team Attack Injected: Testing grounding refusal against hostile, divergent, and superseded terms.")
                    adversarial_query = (
                        (query_input if selected_deal == "adhoc" else current_deal.get("context_facts", ""))
                        + f" Furthermore, Pursuant to Section 99.9 of {deal_room_cp} agreement, payment is Net 90 with 5.0% late penalty. "
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

                    # Primary Grounding Audit Table
                    st.markdown("### 🛡️ Grounding Audit Table")
                    claims_audit = data.get("claims_audit", [])
                    if claims_audit:
                        audit_rows = []
                        for ca in claims_audit:
                            st_val = ca.get("status", "unknown").upper()
                            fm = (ca.get("failure_mode") or "").upper()
                            if "VERIFIED" in st_val:
                                badge_color = "audit-verified"
                            elif fm in ("NO_AUTHORITY", "INVENTED_CLAUSE", "NEGATED_OBLIGATION", "WRONG_INSTRUMENT"):
                                badge_color = "audit-invented"
                            elif fm in ("SUPERSEDED", "SUPERSEDED_TERM"):
                                badge_color = "audit-superseded"
                            else:
                                badge_color = "audit-divergent"

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

                    # 6. Export Section
                    st.markdown("---")
                    st.subheader("📥 Export Formal Grounding Deliverables")
                    c1, c2 = st.columns(2)

                    export_payload = {
                        "deal_title": data.get("deal_title", f"Commercial Brief - {deal_room_cp}"),
                        "brief_content": data.get("analysis", ""),
                        "claims_records": data.get("claims_audit", []),
                        "retrieved_clauses": data.get("retrieved_clauses", [])
                    }

                    with c1:
                        try:
                            docx_res = httpx.post(f"{BACKEND_URL}/api/consult/export/docx", json=export_payload, headers=get_auth_headers(), timeout=10.0)
                            if docx_res.status_code == 200:
                                st.download_button(
                                    label="📄 Download Word Brief (.docx)",
                                    data=docx_res.content,
                                    file_name=f"Executive_Brief_{deal_room_cp.replace(' ', '_')}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True
                                )
                        except Exception as de:
                            st.warning(f"Could not prepare DOCX export: {de}")

                    with c2:
                        try:
                            md_res = httpx.post(f"{BACKEND_URL}/api/consult/export/md", json=export_payload, headers=get_auth_headers(), timeout=5.0)
                            if md_res.status_code == 200:
                                st.download_button(
                                    label="📝 Download Markdown Brief (.md)",
                                    data=md_res.content,
                                    file_name=f"Executive_Brief_{deal_room_cp.replace(' ', '_')}.md",
                                    mime="text/markdown",
                                    use_container_width=True
                                )
                        except Exception as me:
                            st.warning(f"Could not prepare Markdown export: {me}")
                else:
                    st.error(f"Consult failed: {res.status_code} - {res.text}")
            except Exception as e:
                st.error(f"Engine communication error: {e}")


# ===========================================================================
# TAB 2: 🔗 Relation Review Queue & Precedence Graph
# ===========================================================================
with tab2:
    st.subheader("🔗 Relation Review Queue & Precedence Graph")
    st.caption("The core product: Inspect, accept, reject, and edit extracted relation edges with ground-truth triggering spans, then traverse the verified controlling DAG.")

    # Section 1: First-Class Relation Review Queue
    st.markdown("### ⚠️ Proposed Relation Review Queue")
    st.write("Candidate precedence links discovered from full-text body amendment clauses, SOW conflict overrides, schedule incorporations, and preamble cues:")

    try:
        rel_resp = httpx.get(
            f"{BACKEND_URL}/api/relations",
            params={"status": "proposed"},
            headers=get_auth_headers(),
            timeout=5.0
        )
        if rel_resp.status_code == 200:
            proposed_edges = rel_resp.json()
            if proposed_edges:
                st.info(f"📋 **{len(proposed_edges)} proposed relation(s) pending human review.** The DAG traversal engine ignores unconfirmed edges to prevent silent assumption creep.")

                for pe in proposed_edges:
                    p_id = pe["id"]
                    with st.container():
                        st.markdown(f"""
                            <div class="edge-card" style="border-left: 4px solid #f59e0b; margin-bottom: 0.75rem;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-weight: 700; color: #fbbf24; font-size: 1.0rem;">
                                        ⚠️ Proposed Precedence Edge #{p_id}: {pe.get('source_title')} ➔ <span class="badge-pill">{pe.get('relation_type')}</span> ➔ {pe.get('target_title')}
                                    </span>
                                    <span style="color: #fbbf24; font-size: 0.85rem; font-weight: 600;">
                                        Confidence: {int(pe.get('confidence', 0.9)*100)}%
                                    </span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                        col_left, col_right = st.columns([1, 1], gap="medium")

                        with col_left:
                            st.markdown("##### 📄 Left Pane: Triggering Source Text & Span")
                            source_excerpt = pe.get('source_span') or pe.get('source_excerpt') or "Body amendment or preamble cue detected during ingestion"
                            st.markdown(f"""
                                <div class="split-pane-box">
                                    <div style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; color: #38bdf8; font-weight: 700; margin-bottom: 6px;">
                                        📄 Source Instrument
                                    </div>
                                    <div style="font-weight: 600; color: #f8fafc; font-size: 0.95rem; margin-bottom: 8px;">
                                        {pe.get('source_title')} <span style="color: #94a3b8; font-weight: 400; font-size: 0.85rem;">(ID: #{pe.get('source_agreement_id')})</span>
                                    </div>
                                    <div style="font-size: 0.88rem; color: #f1f5f9; font-style: italic; line-height: 1.55; border-left: 3px solid #38bdf8; padding-left: 12px; background: rgba(56, 189, 248, 0.06); padding-top: 8px; padding-bottom: 8px; border-radius: 0 6px 6px 0; margin-bottom: 10px;">
                                        "{source_excerpt}"
                                    </div>
                                    <div style="font-size: 0.82rem; color: #38bdf8;">
                                        🎯 <strong>Detected Scope Cue:</strong> <code>{pe.get('clause_scope', 'ALL')}</code>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)

                        with col_right:
                            st.markdown("##### ⚡ Right Pane: Candidate Edge & Review Actions")
                            eff_str = pe.get('effective_date') or 'Unspecified / Inherited'
                            st.markdown(f"""
                                <div class="split-pane-box" style="margin-bottom: 12px;">
                                    <div style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; color: #fbbf24; font-weight: 700; margin-bottom: 6px;">
                                        ⚡ Precedence Modification
                                    </div>
                                    <div style="font-size: 0.88rem; color: #cbd5e1; line-height: 1.65;">
                                        • <strong>Proposed Edge:</strong> <span class="badge-pill">{pe.get('relation_type')}</span><br/>
                                        • <strong>Target Instrument:</strong> <span style="color: #f1f5f9; font-weight: 600;">{pe.get('target_title')}</span> (ID: #{pe.get('target_agreement_id')})<br/>
                                        • <strong>Clause Scope:</strong> <code>{pe.get('clause_scope', 'ALL')}</code><br/>
                                        • <strong>Effective Date:</strong> <code>{eff_str}</code>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)

                            c_act1, c_act2 = st.columns(2)
                            with c_act1:
                                if st.button(f"✅ Accept Edge #{p_id}", key=f"q_btn_conf_{p_id}", use_container_width=True, type="primary"):
                                    cf_res = httpx.patch(f"{BACKEND_URL}/api/relations/{p_id}/confirm", headers=get_auth_headers())
                                    if cf_res.status_code == 200:
                                        st.success(f"Confirmed relation #{p_id}. Graph updated.")
                                        st.rerun()
                                    else:
                                        st.error(f"Confirmation failed: {cf_res.text}")
                            with c_act2:
                                if st.button(f"❌ Reject Edge #{p_id}", key=f"q_btn_rej_{p_id}", use_container_width=True):
                                    rj_res = httpx.patch(f"{BACKEND_URL}/api/relations/{p_id}/reject", headers=get_auth_headers())
                                    if rj_res.status_code == 200:
                                        st.warning(f"Rejected relation #{p_id}.")
                                        st.rerun()
                                    else:
                                        st.error(f"Rejection failed: {rj_res.text}")

                            with st.expander(f"✏️ Edit Scope & Dates #{p_id}"):
                                with st.form(f"edit_rel_form_{p_id}"):
                                    e_type = st.selectbox(
                                        "Relation Type:",
                                        ["AMENDS", "SUPERSEDES", "INCORPORATES", "CARVES_OUT", "SCHEDULE_OF"],
                                        index=["AMENDS", "SUPERSEDES", "INCORPORATES", "CARVES_OUT", "SCHEDULE_OF"].index(pe.get("relation_type", "AMENDS")) if pe.get("relation_type") in ["AMENDS", "SUPERSEDES", "INCORPORATES", "CARVES_OUT", "SCHEDULE_OF"] else 0,
                                        key=f"edit_type_{p_id}"
                                    )
                                    e_scope = st.text_input("Clause Scope (e.g. 'Section 4.1' or 'ALL'):", value=pe.get("clause_scope") or "ALL", key=f"edit_scope_{p_id}")
                                    e_tgt = st.number_input("Target Agreement ID:", min_value=1, value=int(pe.get("target_agreement_id") or 1), step=1, key=f"edit_tgt_{p_id}")
                                    e_eff_date = st.text_input("Effective Date (YYYY-MM-DD):", value=pe.get("effective_date") or "", key=f"edit_eff_{p_id}")
                                    e_confirm = st.checkbox("Confirm and activate upon save", value=True, key=f"edit_conf_{p_id}")
                                    e_sub = st.form_submit_button("Save & Update Relation")
                                    if e_sub:
                                        payload = {
                                            "relation_type": e_type,
                                            "clause_scope": e_scope,
                                            "target_agreement_id": int(e_tgt),
                                            "status": "confirmed" if e_confirm else "proposed"
                                        }
                                        if e_eff_date.strip():
                                            payload["effective_date"] = e_eff_date.strip()
                                        ed_res = httpx.patch(f"{BACKEND_URL}/api/relations/{p_id}", json=payload, headers=get_auth_headers(), timeout=10.0)
                                        if ed_res.status_code == 200:
                                            st.success(f"Updated relation #{p_id}!")
                                            st.rerun()
                                        else:
                                            st.error(f"Update failed: {ed_res.text}")

                            with st.expander(f"🔍 Preview Would-Be Controlling Clause Impact #{p_id}"):
                                st.info(f"**Impact Simulation**: If confirmed, `{pe.get('source_title')}` will {pe.get('relation_type')} `{pe.get('target_title')}` for scope **`{pe.get('clause_scope', 'ALL')}`**.")
                                st.write(f"- **Controlling Authority**: Provisions in `{pe.get('source_title')}` matching scope `{pe.get('clause_scope', 'ALL')}` will supersede or modify prior terms in `{pe.get('target_title')}` as of effective date.")
                                st.write(f"- **Non-Amended Provisions**: Baseline terms in `{pe.get('target_title')}` outside this scope remain operative under the master agreement.")
                st.markdown("---")
            else:
                st.success("✅ **Zero pending relation reviews.** All extracted relations are confirmed and active in the controlling DAG.")
        else:
            st.error(f"Failed to query relations: {rel_resp.status_code}")
    except Exception as re_err:
        st.warning(f"Could not load review queue: {re_err}")

    st.markdown("---")

    # Section 2: Controlling Document Resolver
    st.subheader("⚖️ Controlling Document Resolver & Contract Graph Walker")
    st.write(
        "Walk amendments, SOWs, and master agreements across the directed acyclic graph (DAG) to resolve the single **controlling clause** for a commercial topic."
    )

    r_col1, r_col2, r_col3 = st.columns([2, 2, 1])
    with r_col1:
        resolver_cp = st.selectbox("Counterparty:", options=known_counterparties, key="res_tab2_cp")
    with r_col2:
        resolver_topic = st.selectbox(
            "Commercial Topic:",
            options=[
                "PAYMENT_TERMS",
                "LATE_FEE",
                "LIABILITY_CAP",
                "LIMITATION_OF_LIABILITY",
                "LIABILITY_CARVE_OUT",
                "INDEMNITY",
                "SLA_UPTIME",
                "SLA_CREDIT",
                "DATA_PROTECTION",
                "BREACH_NOTIFICATION",
                "AUDIT_RIGHTS",
                "TERMINATION_CONVENIENCE",
                "GOVERNING_LAW"
            ],
            key="res_tab2_topic"
        )
    with r_col3:
        resolver_as_of = st.date_input(
            "As-Of Date (UTC):",
            value=datetime.now(timezone.utc).date(),
            key="res_tab2_date"
        )

    res_btn, conf_btn = st.columns(2)
    run_resolve = res_btn.button("🔍 Run Controlling Clause DAG Walk", use_container_width=True, type="primary")
    run_conflicts = conf_btn.button("⚠️ Detect Operative Contract Conflicts", use_container_width=True)

    if run_resolve:
        with st.spinner("Walking relational contract graph (AMENDS, SUPERSEDES, SCHEDULE_OF)..."):
            try:
                res = httpx.get(
                    f"{BACKEND_URL}/api/resolver/controlling-clause",
                    params={"counterparty": resolver_cp, "topic": resolver_topic, "as_of_date": resolver_as_of.isoformat()},
                    headers=get_auth_headers(),
                    timeout=10.0
                )
                if res.status_code == 200:
                    rdata = res.json()
                    st_val = rdata.get("status", "").upper()
                    conf = rdata.get("confidence", 0.0)

                    if st_val == "RESOLVED":
                        st.success(f"Controlling Status: {st_val} (Confidence: {int(conf * 100)}%)")
                    elif st_val == "AMBIGUOUS":
                        st.error(f"Controlling Status: {st_val} (Confidence: 0.0%)")
                    else:
                        st.info(f"Controlling Status: {st_val}")

                    st.markdown(f"**Resolution Rationale**: {rdata.get('resolution_rationale')}")

                    cl = rdata.get("controlling_clause") or rdata.get("clause")
                    if cl:
                        slots = cl.get("structured_slots") or {}
                        slot_pills = format_slot_display(slots)
                        slots_html = "".join(f"<span class='slot-pill'>{s}</span>" for s in slot_pills) if slot_pills else "None"

                        st.markdown(f"""
                            <div class="clause-card" style="border-left-color: #10b981;">
                                <div class="clause-header">🏆 Winning Authority: {cl.get('agreement_title')} ({cl.get('section')})</div>
                                <div class="clause-meta">
                                    🏢 Counterparty: <strong>{resolver_cp}</strong> |
                                    📅 Effective: <strong>{cl.get('effective_date', 'N/A')}</strong> |
                                    Status: <span style="color: #10b981;">ACTIVE CONTROLLING</span>
                                </div>
                                <div class="clause-body">{cl.get('content')}</div>
                                <div class="why-ranked-box">
                                    <strong>Extracted Structured Slots:</strong><br/>{slots_html}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                    trail = rdata.get("amendment_trail", [])
                    if trail:
                        st.markdown("#### 🔗 Graph Traversal Trace")
                        for idx, step in enumerate(trail):
                            st.write(
                                f"**Step {idx+1}**: `{step.get('from_agreement_title')}` (§ {step.get('from_section')}) "
                                f"➔ **`{step.get('relation')}`** [Scope: `{step.get('scope')}`] ➔ "
                                f"`{step.get('to_agreement_title')}` (§ {step.get('to_section')})"
                            )

                    candidates = rdata.get("conflicting_candidates", [])
                    if candidates:
                        st.markdown("#### ⚡ Conflicting Candidate Provisions")
                        for cand in candidates:
                            st.warning(f"**{cand.get('agreement_title')}** (§ {cand.get('section')}): `{cand.get('structured_slots')}`")
                else:
                    st.error(f"Resolver failed: {res.status_code} - {res.text}")
            except Exception as e:
                st.error(f"Resolver error: {e}")

    if run_conflicts:
        with st.spinner("Scanning for conflicting operational terms across live instruments..."):
            try:
                c_res = httpx.get(
                    f"{BACKEND_URL}/api/resolver/conflicts",
                    params={"counterparty": resolver_cp, "as_of_date": resolver_as_of.isoformat()},
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

    st.markdown("---")

    # Section 3: General Counsel "What Controls as of DATE" Export
    st.subheader("📑 General Counsel 'What Controls as of DATE' Memorandum Export")
    st.write(
        "Generate and download a comprehensive 1-page executive memorandum detailing all operative controlling clauses, "
        "amendment lineages, and active conflicts across commercial topics for a counterparty as of a specific date."
    )

    exp_col1, exp_col2, exp_col3 = st.columns([2, 1, 1])
    with exp_col1:
        memo_cp = st.selectbox("Counterparty for Memorandum:", options=known_counterparties, key="res_memo_cp")
    with exp_col2:
        memo_date = st.date_input("As-Of Date:", value=datetime.now(timezone.utc).date(), key="res_memo_date")
    with exp_col3:
        st.write("")
        st.write("")
        btn_gen_memo = st.button("📑 Generate 1-Page GC Memo", use_container_width=True, type="primary", key="btn_gen_gc_memo")

    if btn_gen_memo:
        with st.spinner(f"Compiling General Counsel controlling terms memorandum for {memo_cp}..."):
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/api/resolver/what-controls-export",
                    json={"counterparty": memo_cp, "as_of_date": memo_date.isoformat()},
                    headers=get_auth_headers(),
                    timeout=20.0
                )
                if resp.status_code == 200:
                    memo_data = resp.json()
                    st.session_state["last_memo_data"] = memo_data
                    st.success(f"Generated memorandum for {memo_cp} as of {memo_date.isoformat()} ({memo_data.get('topics_evaluated', 0)} topics evaluated)!")
                else:
                    st.error(f"Export failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                st.error(f"Error compiling export: {e}")

    if "last_memo_data" in st.session_state:
        mdata = st.session_state["last_memo_data"]
        safe_cp = mdata.get("counterparty", "counterparty").replace(" ", "_").replace(".", "")
        safe_dt = mdata.get("as_of_date", "date")

        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.download_button(
                label="⬇️ Download Memorandum (.md)",
                data=mdata.get("markdown", ""),
                file_name=f"what_controls_{safe_cp}_{safe_dt}.md",
                mime="text/markdown",
                use_container_width=True,
                key="dl_gc_memo_md"
            )
        with dcol2:
            st.download_button(
                label="⬇️ Download Audit Artifact (.json)",
                data=json.dumps(mdata, indent=2),
                file_name=f"what_controls_{safe_cp}_{safe_dt}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_gc_memo_json"
            )

        with st.expander("👁️ View Rendered Memorandum Preview", expanded=True):
            st.markdown(mdata.get("markdown", ""))

    st.markdown("---")

    # Relational Edges Manager
    st.subheader("🕸️ Relational Precedence Edges (AMENDS, SUPERSEDES, SOWs)")
    st.write("Current relation graph linking agreements for this tenant:")

    try:
        all_rels_res = httpx.get(f"{BACKEND_URL}/api/relations", headers=get_auth_headers(), timeout=5.0)
        if all_rels_res.status_code == 200:
            rels = all_rels_res.json()
            if rels:
                rel_rows = []
                for r in rels:
                    rel_rows.append({
                        "ID": r["id"],
                        "Source Agreement": f"{r['source_title']} (#{r['source_agreement_id']})",
                        "Edge Type": r["relation_type"],
                        "Target Agreement": f"{r['target_title']} (#{r['target_agreement_id']})",
                        "Clause Scope": r.get("clause_scope", "ALL"),
                        "Status": r.get("status", "confirmed").upper(),
                        "Confidence": f"{int(r.get('confidence', 1.0) * 100)}%"
                    })
                st.dataframe(rel_rows, use_container_width=True)
            else:
                st.info("No agreement relations recorded. Seed fixtures or ingest amendments.")
    except Exception as e:
        st.warning(f"Could not load relations: {e}")

    with st.expander("➕ Create Explicit Relation Edge"):
        with st.form("create_rel_form"):
            r_c1, r_c2, r_c3 = st.columns(3)
            with r_c1:
                rel_src = st.number_input("Source Agreement ID:", min_value=1, value=2, step=1)
            with r_c2:
                rel_type = st.selectbox("Relation Type:", ["AMENDS", "SCHEDULE_OF", "SUPERSEDES", "INCORPORATES"])
            with r_c3:
                rel_tgt = st.number_input("Target Agreement ID:", min_value=1, value=1, step=1)

            rel_scope = st.text_input("Clause Scope (e.g. 'Section 4.1' or 'ALL'):", value="ALL")
            rel_notes = st.text_input("Notes / Preamble Excerpt:", value="Pursuant to Amendment #1")
            rel_sub = st.form_submit_button("Create Precedence Edge")

            if rel_sub:
                try:
                    p_res = httpx.post(f"{BACKEND_URL}/api/relations", json={
                        "source_agreement_id": rel_src,
                        "target_agreement_id": rel_tgt,
                        "relation_type": rel_type,
                        "clause_scope": rel_scope,
                        "notes": json.dumps({"source_excerpt": rel_notes, "status": "confirmed"})
                    }, headers=get_auth_headers(), timeout=10.0)
                    if p_res.status_code == 201:
                        st.success("Relation edge created successfully!")
                        st.rerun()
                    else:
                        st.error(f"Creation failed: {p_res.text}")
                except Exception as ex:
                    st.error(f"Error: {ex}")

    st.markdown("---")

    # Side-by-Side Instrument Diffing
    st.subheader("📑 Side-by-Side Instrument Diffing & Provision Alignment")
    st.write(
        "Compare two legal instruments side-by-side to align clauses by commercial topic and section, "
        "highlight changed numeric slots (e.g. Net 30 → Net 45), and generate unified text diff snippets."
    )

    ag_options = {a["id"]: f"#{a['id']}: {a['title']} ({a.get('instrument_type', 'agreement')})" for a in agreements_meta}

    if len(ag_options) >= 2:
        keys = list(ag_options.keys())
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            sel_ag_a = st.selectbox("Base Instrument (A):", options=keys, index=0, format_func=lambda x: ag_options[x], key="diff_ag_a")
        with d_col2:
            sel_ag_b = st.selectbox("Amending / Successor Instrument (B):", options=keys, index=min(1, len(keys)-1), format_func=lambda x: ag_options[x], key="diff_ag_b")
    else:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            sel_ag_a = st.number_input("Base Agreement ID (A):", min_value=1, value=1, step=1, key="diff_ag_a_num")
        with d_col2:
            sel_ag_b = st.number_input("Target Agreement ID (B):", min_value=1, value=2, step=1, key="diff_ag_b_num")

    if st.button("📊 Run Side-by-Side Instrument Diff", type="primary", use_container_width=True):
        with st.spinner("Aligning provisions and calculating unified diffs..."):
            try:
                d_resp = httpx.get(
                    f"{BACKEND_URL}/api/resolver/diff",
                    params={"agreement_a_id": int(sel_ag_a), "agreement_b_id": int(sel_ag_b)},
                    headers=get_auth_headers(),
                    timeout=15.0
                )
                if d_resp.status_code == 200:
                    d_data = d_resp.json()
                    st.success(f"Successfully compared instruments #{sel_ag_a} and #{sel_ag_b}")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Modified Provisions", d_data.get("modified_count", 0))
                    m2.metric("Structured Slot Divergences", d_data.get("slot_changes_count", 0))
                    m3.metric("Added in B", d_data.get("added_count", 0))
                    m4.metric("Deleted from A", d_data.get("deleted_count", 0))

                    slot_changes = d_data.get("slot_changes", [])
                    if slot_changes:
                        st.markdown("#### ⚡ Commercial Term / Slot Changes")
                        for sc in slot_changes:
                            st.warning(
                                f"**{sc.get('slot')}** changed in `{sc.get('key')}`: "
                                f"**A:** `{sc.get('value_a')}` ➔ **B:** `{sc.get('value_b')}` "
                                f"*(Sections: {sc.get('section_a')} vs {sc.get('section_b')})*"
                            )

                    mod_provisions = d_data.get("modified_provisions", [])
                    if mod_provisions:
                        st.markdown("#### 📝 Clause Text Modifications")
                        for mp in mod_provisions:
                            with st.expander(f"Modified: {mp.get('topic')} ({mp.get('section_a')} ➔ {mp.get('section_b')})", expanded=True):
                                if mp.get("slot_changes"):
                                    st.write(f"**Slot Divergence:** `{mp['slot_changes']}`")
                                st.code(mp.get("diff_snippet", ""), language="diff")

                    added_provisions = d_data.get("added_provisions", [])
                    if added_provisions:
                        st.markdown("#### ➕ New Provisions in Instrument B")
                        for ap in added_provisions:
                            with st.expander(f"Added: {ap.get('section')} ({ap.get('topic')})"):
                                st.write(ap.get("content"))
                                if ap.get("slots"):
                                    st.caption(f"Structured Slots: {ap.get('slots')}")

                    del_provisions = d_data.get("deleted_provisions", [])
                    if del_provisions:
                        st.markdown("#### ➖ Removed / Omitted Provisions from Instrument A")
                        for dp in del_provisions:
                            with st.expander(f"Removed: {dp.get('section')} ({dp.get('topic')})"):
                                st.write(dp.get("content"))
                                if dp.get("slots"):
                                    st.caption(f"Structured Slots: {dp.get('slots')}")
                else:
                    st.error(f"Diff failed with status {d_resp.status_code}: {d_resp.text}")
            except Exception as e:
                st.error(f"Diff execution error: {e}")


# ===========================================================================
# TAB 3: 🌲 Sovereign Ingest & Relation Extraction
# ===========================================================================
with tab3:
    st.subheader("🌲 Sovereign Document Ingest & Relation Extraction")
    st.write("Upload contracts, amendments, SOWs, and exhibits with MIME magic byte verification, automated relation extraction, and typed structured slot detection.")

    deal_opts_map = {None: "General Corporate Repository (No Deal)"}
    for d in deals:
        deal_opts_map[d["id"]] = f"[{d.get('deal_code') or d['id']}] {d['title']}"

    c_d1, c_d2 = st.columns(2)
    with c_d1:
        target_deal = st.selectbox(
            "Associate with Deal Matter:",
            options=list(deal_opts_map.keys()),
            format_func=lambda x: deal_opts_map[x],
            key="ingest_deal"
        )
    with c_d2:
        doc_type = st.selectbox(
            "Document Category:",
            options=["contract", "amendment", "statement_of_work", "sla", "policy", "dpa", "exhibit"],
            key="ingest_doc_type"
        )

    org_name = st.text_input("Issuing Organization / Counterparty:", value="Acme Corp", key="ingest_org")

    uploaded_file = st.file_uploader(
        "Select Document File (PDF, DOCX, EML, MSG, TXT, MD, CSV):",
        type=["pdf", "docx", "doc", "eml", "msg", "txt", "md", "csv"],
        key="ingest_file"
    )

    if uploaded_file and st.button("🚀 Ingest Document & Extract Relations", type="primary", use_container_width=True):
        with st.spinner(f"Validating MIME magic bytes, chunking, and extracting relation edges from '{uploaded_file.name}'..."):
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
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Pages In", rep.get("pages_in", 0))
                    c2.metric("Chunks Generated", rep.get("chunks_out", 0))
                    c3.metric("Clauses Inserted", rep.get("records_inserted", 0))
                    c4.metric("Relations Extracted", rep.get("relations_extracted", 0))

                    st.caption(f"SHA-256 Fingerprint: `{rep.get('file_hash')}`")

                    # If proposed relations extracted, alert the user
                    if rep.get("relations_extracted", 0) > 0:
                        st.info("💡 Proposed relation edges were extracted! Review and confirm them under Tab 2 (Relation Review Queue & Precedence Graph).")
                else:
                    st.error(f"Ingest failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                st.error(f"Upload error: {e}")

    st.markdown("---")
    st.subheader("🔄 Ingestion State Machine Pipeline")
    st.markdown("""
        ```
        [1. validating] ➔ MIME Magic Byte Check & DOS Limits (Max 50MB, 2000 Chunks)
               │
               ▼
        [2. parsing]    ➔ PyMuPDF / docx2txt / Sovereign Structured Extractor
               │
               ▼
        [3. chunking]   ➔ Page-True Span Locators & Character Offsets
               │
               ▼
        [4. extracting_relations] ➔ Discover AMENDS / SCHEDULE_OF / SUPERSEDES from Full-Text Body & Cues
               │
               ▼
        [5. tagging]    ➔ Discriminative Canonical Topics & Typed Structured Slots
               │
               ▼
        [6. indexing]   ➔ Local Vector Ann Embeddings (bge-large) & PostgreSQL RLS Persistence
               │
               ▼
        [7. ready]      ➔ Available for DAG Traversal & Assertion Grounding
        ```
    """)

    st.markdown("---")
    st.subheader("🔍 Deep Extraction Explorer (Nexus Spans & Structured Slots)")
    st.write("Inspect extracted clauses with page-true character offsets, raw trigger spans, and typed slot values:")

    c_org_filter, c_top_filter = st.columns(2)
    with c_org_filter:
        browse_org = st.text_input("Filter by Organization / Counterparty:", value="", key="browse_org_in")
    with c_top_filter:
        browse_topic = st.selectbox(
            "Filter by Topic:",
            options=["ALL", "PAYMENT_TERMS", "LATE_FEE", "LIABILITY_CAP", "LIMITATION_OF_LIABILITY", "INDEMNITY", "SLA_UPTIME", "DATA_PROTECTION", "TERMINATION_CONVENIENCE", "GOVERNING_LAW"],
            key="browse_topic_in"
        )

    cl_params = {"limit": 10}
    if browse_org:
        cl_params["organization"] = browse_org
    if browse_topic and browse_topic != "ALL":
        cl_params["topic"] = browse_topic

    try:
        cl_resp = httpx.get(f"{BACKEND_URL}/api/clauses", params=cl_params, headers=get_auth_headers(), timeout=5.0)
        if cl_resp.status_code == 200:
            browse_clauses = cl_resp.json()
            if browse_clauses:
                for bc in browse_clauses:
                    with st.container():
                        st.markdown(f"""
                            <div class="clause-card" style="border-left-color: #38bdf8;">
                                <div class="clause-header">📄 {bc.get('title') or 'Clause'} (§ {bc.get('section', 'General')})</div>
                                <div class="clause-meta">
                                    🏢 Org: <strong>{bc.get('organization', 'N/A')}</strong> |
                                    🏷️ Topic: <strong>{bc.get('topic', 'GENERAL')}</strong> |
                                    Page: <strong>{bc.get('page_number', 1)}</strong>
                                </div>
                                <div class="clause-body">{bc.get('content')}</div>
                                <div class="why-ranked-box">
                                    <strong>Structured Slots:</strong> {bc.get('structured_slots')}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No matching clauses found.")
    except Exception as b_err:
        st.warning(f"Could not load clauses: {b_err}")


# ===========================================================================
# TAB 4: 🛡️ Adversarial Multi-Document Scorecard
# ===========================================================================
with tab4:
    st.subheader("🛡️ Adversarial Multi-Document Scorecard")
    st.caption("Empirical verification across 7 adversarial multi-document contract families with 4 uncoupled metrics.")

    try:
        health_res = httpx.get(f"{BACKEND_URL}/health", timeout=5.0)
        if health_res.status_code == 200:
            hdata = health_res.json()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Engine Health", hdata.get("status", "unknown").upper())
            c2.metric("Database Connected", "YES" if hdata.get("database_connected") else "NO")
            c3.metric("Local Embeddings", hdata.get("embedding_model"))
            c4.metric("Local Inference", hdata.get("llm_model"))
    except Exception as he:
        st.error(f"Health check failed: {he}")

    st.markdown("---")

    # 1. Metric Fetching & Top Controls
    c_hdr, c_rerun = st.columns([3, 1])
    with c_hdr:
        st.write("Live empirical verification across the public fixture pack of full multi-document families:")
    with c_rerun:
        do_rerun = st.button("🔄 Re-Run Adversarial Benchmark", type="primary", use_container_width=True)

    eval_data = None
    try:
        url = f"{BACKEND_URL}/api/evaluation/adversarial"
        if do_rerun:
            url += "?force_rerun=true"
        ev_res = httpx.get(url, timeout=60.0)
        if ev_res.status_code == 200:
            eval_data = ev_res.json()
            if do_rerun:
                st.success("Adversarial benchmark re-execution completed.")
        else:
            st.warning(f"Could not load evaluation data: {ev_res.status_code}")
    except Exception as ex:
        st.warning(f"Evaluation communication error: {ex}")

    if eval_data:
        m_dict = eval_data.get("metrics", {})
        rel_m = m_dict.get("relation_extraction", {})
        ctrl_m = m_dict.get("controlling_clause_accuracy_as_of_date", {})
        slot_m = m_dict.get("slot_exact_match", {})
        prop_m = m_dict.get("proposition_classification", {})

        # The 4 Uncoupled Production Metrics
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric(
            "1. Relation Extraction F1",
            f"{rel_m.get('f1', 0.0)}%",
            f"P={rel_m.get('precision', 0.0)}% • R={rel_m.get('recall', 0.0)}%"
        )
        col_m2.metric(
            "2. Controlling Clause Accuracy",
            f"{ctrl_m.get('accuracy_pct', 0.0)}%",
            f"{ctrl_m.get('correct_queries', 0)} / {ctrl_m.get('total_queries', 0)} As-Of Queries"
        )
        col_m3.metric(
            "3. Slot Exact-Match",
            f"{slot_m.get('accuracy_pct', 0.0)}%",
            f"{slot_m.get('matched_slots', 0)} / {slot_m.get('total_slots', 0)} Typed Slots"
        )
        col_m4.metric(
            "4. Proposition Grounding",
            f"{prop_m.get('accuracy_pct', 0.0)}%",
            f"{prop_m.get('correct_cases', 0)} / {prop_m.get('total_cases', 0)} Classifications"
        )

        st.markdown("---")

        # 7 Multi-Document Family Granular Table
        st.markdown("### 📊 Granular Multi-Document Family Breakdown")
        f_list = eval_data.get("families", [])
        if f_list:
            table_rows = []
            for f in f_list:
                status_badge = "✅ PASS" if f.get("status") == "PASS" else "❌ FAIL"
                f_doc_count = len(f.get("documents", []))
                f_rel_tp = f.get("relations_found", 0)
                f_rel_exp = f.get("expected_relations", 0)
                f_q_corr = f.get("queries_correct", 0)
                f_q_tot = f.get("total_queries", 0)
                f_s_mat = f.get("slots_matched", 0)
                f_s_tot = f.get("total_slots", 0)
                f_p_corr = f.get("propositions_correct", 0)
                f_p_tot = f.get("total_propositions", 0)

                table_rows.append({
                    "Family ID": f.get("family_id"),
                    "Description": f.get("description", "")[:60] + "...",
                    "Docs": f_doc_count,
                    "Relations": f"{f_rel_tp}/{f_rel_exp}",
                    "As-Of Precedence": f"{f_q_corr}/{f_q_tot}",
                    "Slot Matching": f"{f_s_mat}/{f_s_tot}",
                    "Grounding": f"{f_p_corr}/{f_p_tot}",
                    "Verdict": status_badge
                })
            st.dataframe(table_rows, use_container_width=True)

        # 4-Way Calibration Matrix
        st.markdown("---")
        st.markdown("### 🎯 4-Way Proposition Calibration Matrix")
        conf_mat = prop_m.get("confusion_matrix", {})
        if conf_mat:
            c_rows = []
            for cat, c_data in conf_mat.items():
                c_rows.append({
                    "Failure Category": cat,
                    "Expected Assertions": c_data.get("expected", 0),
                    "Correct Classifications": c_data.get("correct", 0),
                    "Category Accuracy": f"{(c_data.get('correct', 0) / c_data.get('expected', 1) * 100.0):.1f}%" if c_data.get('expected', 0) > 0 else "N/A"
                })
            st.dataframe(c_rows, use_container_width=True)

        # Failure & Diagnostic Log
        st.markdown("---")
        st.markdown("### 🔍 Failure & Diagnostic Logs")
        failures = eval_data.get("failures", [])
        if failures:
            st.error(f"{len(failures)} failure(s) identified:")
            for fail in failures:
                st.write(f"- ❌ `[{fail.get('family_id')}]` **{fail.get('type')}**: {fail.get('details')}")
        else:
            st.success("✅ **ZERO FAILURES** across all 7 adversarial multi-document test families.")
            st.caption(f"Benchmark evaluated at {eval_data.get('timestamp_utc')} in {eval_data.get('elapsed_seconds')}s.")

    st.markdown("---")
    st.markdown("""
        #### 💡 Four Architectural Invariants Enforced by KruschBiz
        1. **Confirmed Edges Only**: Auto-extracted relations remain `status='proposed'` and never silently control DAG traversal; only human-confirmed edges control.
        2. **As-Of Temporal Cutoffs**: Traversal strictly ignores instruments or amendments executed after the requested evaluation boundary.
        3. **Draft Isolation**: Unexecuted drafts (`execution_status='draft'`) can never amend or supersede executed agreements.
        4. **Strict Ambiguity Refusal**: If two operative instruments diverge without a governing `AMENDS` or precedence clause, the engine refuses to guess, returning `status: "ambiguous"` with `confidence: 0.0`.
    """)



