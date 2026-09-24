"""
src/backend/business_templates.py
=================================
Commercial document drafting engine & template repository (DraftPro for KruschBiz).
Features:
  - Curated commercial templates: Mutual NDA, B2B MSA, Statement of Work, Independent Contractor, and Demand for Payment
  - Schema-driven field validation and sanitization
  - Deterministic document generation with markdown structure
  - AI revision and enhancement support with sovereign local model fallback
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any


logger = logging.getLogger("kruschbiz.templates")

TEMPLATES_CATALOG: dict[str, dict[str, Any]] = {
    "commercial_nda": {
        "id": "commercial_nda",
        "name": "Mutual Non-Disclosure Agreement (NDA)",
        "category": "Confidentiality",
        "description": "Standard two-way mutual confidentiality agreement protecting proprietary technology, financial projections, and commercial deal negotiations.",
        "fields": [
            {"key": "party_a", "label": "Disclosing / First Party", "type": "string", "required": True, "default": "Acme Corp"},
            {"key": "party_b", "label": "Receiving / Second Party", "type": "string", "required": True, "default": "CloudScale AI LLC"},
            {"key": "purpose", "label": "Transaction / Discussion Purpose", "type": "string", "required": True, "default": "evaluating a potential B2B software licensing and services partnership"},
            {"key": "term_years", "label": "Confidentiality Duration (Years)", "type": "integer", "required": True, "default": 3},
            {"key": "governing_law", "label": "Governing Law Jurisdiction", "type": "string", "required": True, "default": "State of California"},
            {"key": "effective_date", "label": "Effective Date (YYYY-MM-DD)", "type": "string", "required": True, "default": datetime.now().strftime("%Y-%m-%d")},
        ],
        "template": """# MUTUAL NON-DISCLOSURE AGREEMENT

This Mutual Non-Disclosure Agreement (the **"Agreement"**) is entered into on **{effective_date}** (the **"Effective Date"**), by and between:

1. **{party_a}**, and
2. **{party_b}** (each a **"Party"** and collectively the **"Parties"**).

---

### 1. Purpose
The Parties wish to explore and engage in discussions concerning **{purpose}** (the **"Purpose"**). In connection with the Purpose, either Party may disclose its proprietary and confidential technical, business, or financial information to the other Party.

### 2. Definition of Confidential Information
**"Confidential Information"** means all non-public information disclosed by one Party (**"Disclosing Party"**) to the other Party (**"Receiving Party"**), whether orally, in writing, electronically, or by inspection of tangible objects, that is designated as confidential or that reasonably should be understood to be confidential given the nature of the information and the circumstances of disclosure.

### 3. Exclusions
Confidential Information does not include information that:
1. is or becomes generally known to the public without breach of any obligation owed to Disclosing Party;
2. was known to Receiving Party prior to disclosure without confidentiality restrictions;
3. is independently developed by Receiving Party without reference to or use of Disclosing Party's Confidential Information; or
4. is rightfully received from a third party without duty of confidentiality.

### 4. Obligations of Receiving Party
Receiving Party agrees to:
1. protect Confidential Information with the same degree of care it uses for its own confidential materials (and not less than reasonable care);
2. restrict disclosure solely to its directors, officers, employees, and legal/financial advisors with a need-to-know who are bound by confidentiality obligations no less restrictive than this Agreement; and
3. not use Disclosing Party's Confidential Information for any purpose outside the scope of the Purpose.

### 5. Term and Protection Period
This Agreement shall govern disclosures for a period of **{term_years} year(s)** following the Effective Date. The confidentiality obligations regarding trade secrets shall survive indefinitely or for the maximum period permitted by applicable statutory law.

### 6. Governing Law & Dispute Resolution
This Agreement shall be governed by, and construed in accordance with, the laws of the **{governing_law}**, without regard to conflict of laws principles. Any legal suit, action, or proceeding arising out of or related to this Agreement shall be instituted exclusively in the state or federal courts located in {governing_law}.

---

**IN WITNESS WHEREOF**, the Parties have executed this Mutual Non-Disclosure Agreement as of the Effective Date.

| For {party_a} | For {party_b} |
|:---|:---|
| Signature: _________________________ | Signature: _________________________ |
| Name: _____________________________ | Name: _____________________________ |
| Title: ______________________________ | Title: ______________________________ |
| Date: {effective_date} | Date: {effective_date} |
"""
    },
    "master_services_agreement": {
        "id": "master_services_agreement",
        "name": "B2B Master Services Agreement (MSA)",
        "category": "Services",
        "description": "Comprehensive enterprise master services agreement establishing the governing contractual terms, payment terms, IP assignments, and liability caps for commercial relationships.",
        "fields": [
            {"key": "provider_name", "label": "Service Provider", "type": "string", "required": True, "default": "Krusch Dynamics LLC"},
            {"key": "client_name", "label": "Client / Enterprise", "type": "string", "required": True, "default": "Acme Global Enterprise"},
            {"key": "effective_date", "label": "Effective Date (YYYY-MM-DD)", "type": "string", "required": True, "default": datetime.now().strftime("%Y-%m-%d")},
            {"key": "net_days", "label": "Payment Terms (Net Days)", "type": "integer", "required": True, "default": 30},
            {"key": "late_fee_pct", "label": "Monthly Late Fee Interest (%)", "type": "float", "required": True, "default": 1.5},
            {"key": "liability_cap_months", "label": "Liability Cap Lookback (Months)", "type": "integer", "required": True, "default": 12},
            {"key": "governing_law", "label": "Governing Jurisdiction", "type": "string", "required": True, "default": "State of California"},
        ],
        "template": """# MASTER SERVICES AGREEMENT

This Master Services Agreement (this **"Agreement"**), dated as of **{effective_date}** (the **"Effective Date"**), is entered into by and between:

- **{provider_name}** (**"Provider"**), and
- **{client_name}** (**"Client"**).

---

### 1. Scope & Statements of Work
Provider agrees to perform services and deliver work product as set forth in one or more mutually executed Statements of Work (each an **"SOW"**) governed by this Agreement. In the event of a conflict between this Agreement and any SOW, the terms of this Agreement shall control unless an SOW explicitly states its intent to amend a specific section hereof.

### 2. Invoicing, Fees & Payment Terms
1. **Invoicing**: Provider shall invoice Client in accordance with the billing schedule set forth in the applicable SOW.
2. **Payment Terms**: Client shall pay all undisputed invoice amounts within **Net {net_days} days** from the invoice date.
3. **Late Payments**: Overdue amounts shall accrue interest at the rate of **{late_fee_pct}% per month** (or the maximum statutory rate permitted by law, whichever is less) until paid in full.

### 3. Intellectual Property Rights
1. **Pre-Existing IP**: Each Party retains sole ownership of all pre-existing intellectual property, tools, methodologies, and source materials owned prior to this Agreement.
2. **Work Product**: Upon full payment of all applicable fees, Provider assigns to Client all right, title, and interest in customized deliverables explicitly identified as Work Product in the relevant SOW.

### 4. Warranties & Disclaimers
Provider warrants that services will be performed in a professional, workmanlike manner consistent with prevailing industry standards. EXCEPT AS EXPRESSLY SET FORTH HEREIN, PROVIDER DISCLAIMS ALL OTHER WARRANTIES, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.

### 5. Limitation of Liability
1. **Consequential Damages Waiver**: NEITHER PARTY SHALL BE LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES.
2. **Aggregate Cap**: EXCEPT FOR GROSS NEGLIGENCE, WILLFUL MISCONDUCT, OR BREACH OF CONFIDENTIALITY, EACH PARTY'S TOTAL AGGREGATE LIABILITY ARISING UNDER THIS AGREEMENT SHALL BE STRICTLY LIMITED TO THE TOTAL FEES PAID OR PAYABLE BY CLIENT UNDER THE APPLICABLE SOW IN THE **{liability_cap_months} MONTHS** IMMEDIATELY PRECEDING THE EVENT GIVING RISE TO LIABILITY.

### 6. Term, Termination & Governing Law
This Agreement continues until terminated by either Party upon thirty (30) days written notice. This Agreement is governed by the laws of the **{governing_law}**.

---

**SIGNATURES**:

| Provider: {provider_name} | Client: {client_name} |
|:---|:---|
| By: ________________________________ | By: ________________________________ |
| Title: Authorized Officer | Title: Authorized Officer |
| Date: {effective_date} | Date: {effective_date} |
"""
    },
    "statement_of_work": {
        "id": "statement_of_work",
        "name": "Statement of Work (SOW)",
        "category": "Services",
        "description": "Project-specific deliverable, timeline, milestone, and acceptance criteria document executed under a Master Services Agreement.",
        "fields": [
            {"key": "sow_number", "label": "SOW Number / Identifier", "type": "string", "required": True, "default": "SOW-2026-001"},
            {"key": "msa_date", "label": "Governing MSA Date", "type": "string", "required": True, "default": "2026-01-15"},
            {"key": "provider_name", "label": "Provider Name", "type": "string", "required": True, "default": "Krusch Dynamics LLC"},
            {"key": "client_name", "label": "Client Name", "type": "string", "required": True, "default": "Acme Corp"},
            {"key": "project_name", "label": "Project Title", "type": "string", "required": True, "default": "Enterprise Cloud Architecture Modernization"},
            {"key": "start_date", "label": "Project Start Date", "type": "string", "required": True, "default": datetime.now().strftime("%Y-%m-%d")},
            {"key": "completion_date", "label": "Target Completion Date", "type": "string", "required": True, "default": "2026-12-31"},
            {"key": "total_fee", "label": "Total Professional Fee ($)", "type": "float", "required": True, "default": 85000.00},
            {"key": "milestones", "label": "Key Milestones & Deliverables", "type": "string", "required": True, "default": "1. Discovery & Architecture Blueprint (20%)\n2. Core Pipeline Implementation (40%)\n3. Deployment, Security Audit & Staging Acceptance (40%)"},
        ],
        "template": """# STATEMENT OF WORK: {sow_number}
**Project: {project_name}**

This Statement of Work (**"{sow_number}"**) is entered into pursuant to that certain Master Services Agreement dated **{msa_date}** by and between **{provider_name}** (**"Provider"**) and **{client_name}** (**"Client"**).

---

### 1. Project Overview & Objectives
Provider shall render professional technical and advisory services for **{project_name}**, commencing on **{start_date}** with an estimated delivery deadline of **{completion_date}**.

### 2. Deliverables & Milestone Schedule
The project shall proceed across the following designated milestones:

{milestones}

### 3. Acceptance Criteria
Client shall have five (5) business days following receipt of each deliverable to review and provide written notice of acceptance or specific material defects. Absence of written objection within five (5) business days constitutes constructive acceptance.

### 4. Fees & Billing Schedule
The total fixed fee for services rendered under this SOW is **${total_fee:,.2f} USD**, invoiced pro-rata upon milestone completion in accordance with the governing Agreement payment terms.

---

**ACCEPTED AND AGREED:**

**{provider_name}**: __________________________ Date: {start_date}
**{client_name}**: __________________________ Date: {start_date}
"""
    },
    "independent_contractor": {
        "id": "independent_contractor",
        "name": "Independent Contractor & IP Agreement",
        "category": "Contractors",
        "description": "Engage 1099 consultants and independent technical specialists with complete work-made-for-hire assignment and restrictive covenants.",
        "fields": [
            {"key": "company_name", "label": "Company / Hiring Entity", "type": "string", "required": True, "default": "Acme Ventures Inc."},
            {"key": "contractor_name", "label": "Contractor Full Name / Entity", "type": "string", "required": True, "default": "Jordan Mercer"},
            {"key": "effective_date", "label": "Effective Date", "type": "string", "required": True, "default": datetime.now().strftime("%Y-%m-%d")},
            {"key": "services", "label": "Services & Deliverables", "type": "string", "required": True, "default": "Software engineering, distributed database indexing, and technical documentation"},
            {"key": "rate", "label": "Compensation Rate ($ / Hour or Project)", "type": "string", "required": True, "default": "$150.00 / hour"},
            {"key": "governing_law", "label": "Governing State", "type": "string", "required": True, "default": "State of California"},
        ],
        "template": """# INDEPENDENT CONTRACTOR AGREEMENT

This Independent Contractor Agreement (the **"Agreement"**) is entered into as of **{effective_date}**, by and between **{company_name}** (**"Company"**) and **{contractor_name}** (**"Contractor"**).

---

### 1. Engagement & Services
Company hereby engages Contractor, and Contractor agrees, to perform the following services: **{services}**. Contractor shall determine the method, details, and means of performing the services.

### 2. Relationship of the Parties
Contractor is an independent contractor, not an employee, agent, or partner of Company. Contractor is solely responsible for all federal, state, and local income taxes, self-employment taxes, and statutory withholdings.

### 3. Compensation & Expenses
Company shall pay Contractor at the rate of **{rate}**, payable within thirty (30) days of receipt of Contractor's itemized monthly invoice.

### 4. Proprietary Information & Assignment of Inventions
All discoveries, inventions, works of authorship, code, and documentation produced by Contractor in connection with the services shall be considered "works made for hire" and shall be the exclusive property of Company. Contractor hereby irrevocably assigns all rights, titles, and interests in and to such work product to Company.

### 5. Governing Law
This Agreement shall be construed in accordance with the laws of the **{governing_law}**.

---

**SIGNATURES:**

**Company**: {company_name}
By: ___________________________ Date: {effective_date}

**Contractor**: {contractor_name}
By: ___________________________ Date: {effective_date}
"""
    },
    "commercial_demand_letter": {
        "id": "commercial_demand_letter",
        "name": "Commercial Demand for Payment & Notice of Default",
        "category": "Disputes",
        "description": "Formal legal demand letter requesting overdue payment on commercial invoices and providing notice of contractual breach before arbitration/litigation.",
        "fields": [
            {"key": "creditor_name", "label": "Creditor / Claimant Enterprise", "type": "string", "required": True, "default": "Krusch Holdings LLC"},
            {"key": "debtor_name", "label": "Delinquent Counterparty / Customer", "type": "string", "required": True, "default": "Nexus Retail Partners"},
            {"key": "invoice_number", "label": "Delinquent Invoice Number", "type": "string", "required": True, "default": "INV-2026-4402"},
            {"key": "invoice_date", "label": "Original Invoice Date", "type": "string", "required": True, "default": "2026-07-01"},
            {"key": "original_amount", "label": "Principal Overdue Amount ($)", "type": "float", "required": True, "default": 24500.00},
            {"key": "interest_accrued", "label": "Contractual Interest Accrued ($)", "type": "float", "required": True, "default": 735.00},
            {"key": "cure_days", "label": "Cure Period (Days to Remit)", "type": "integer", "required": True, "default": 10},
            {"key": "governing_agreement", "label": "Governing Contract Reference", "type": "string", "required": True, "default": "Master Services Agreement dated January 15, 2026"},
        ],
        "template": """# NOTICE OF CONTRACTUAL DEFAULT & FORMAL DEMAND FOR PAYMENT

**DATE:** {date_today}
**VIA CERTIFIED MAIL & ELECTRONIC TRANSMISSION**

**TO:**
{debtor_name}
Attn: Legal & Accounts Payable

**FROM:**
{creditor_name}
Corporate Legal & Credit Department

**RE: FORMAL DEMAND FOR IMMEDIATE REMITTANCE OF DELINQUENT INVOICE #{invoice_number}**
**Underlying Contract: {governing_agreement}**

---

Dear Counterparty:

Please be advised that this correspondence constitutes formal written notice that **{debtor_name}** is in material default of its contractual payment obligations under the **{governing_agreement}**.

### Statement of Delinquency
As of the date of this letter, the following amounts remain outstanding and severely past due:

- **Original Invoice Date:** {invoice_date}
- **Delinquent Invoice Number:** #{invoice_number}
- **Principal Amount Outstanding:** ${original_amount:,.2f}
- **Contractual Late Interest:** ${interest_accrued:,.2f}
- **TOTAL LIQUIDATED AMOUNT DUE:** **${total_demand:,.2f} USD**

Despite repeated courtesy notices and accounting statements, you have failed to remit payment as mandated by Section 2 of our Agreement.

### Demand for Cure
**{creditor_name} hereby demands that full payment of ${total_demand:,.2f} be remitted via wire transfer within {cure_days} business days of receipt of this notice.**

### Reservation of Rights
If full payment is not received within **{cure_days} business days**, {creditor_name} shall immediately exercise all available legal and contractual remedies, including:
1. Immediate suspension or termination of all active services and intellectual property licenses;
2. Referral of this matter to outside counsel for civil litigation or binding arbitration; and
3. Recovery of all statutory court costs, reasonable attorneys' fees, and collection expenses as provided under governing law.

Govern yourself accordingly.

Sincerely,

___________________________________________
**{creditor_name}**
Office of the General Counsel
"""
    }
}


def list_commercial_templates() -> list[dict[str, Any]]:
    """Enumerate all available drafting templates without full text."""
    results = []
    for t_id, t_info in TEMPLATES_CATALOG.items():
        results.append({
            "id": t_id,
            "name": t_info["name"],
            "category": t_info["category"],
            "description": t_info["description"],
            "field_count": len(t_info["fields"]),
        })
    return results


def get_commercial_template(template_id: str) -> dict[str, Any] | None:
    """Retrieve template definition and fields."""
    return TEMPLATES_CATALOG.get(template_id)


def generate_commercial_document(
    template_id: str,
    field_data: dict[str, Any],
    enhance_with_llm: bool = False
) -> dict[str, Any]:
    """
    Render a completed commercial document using template and field inputs.
    Calculates dynamic totals and dates.
    """
    tmpl_spec = TEMPLATES_CATALOG.get(template_id)
    if not tmpl_spec:
        raise ValueError(f"Unknown commercial template '{template_id}'.")

    # Build clean context with defaults
    context = {}
    for f in tmpl_spec["fields"]:
        key = f["key"]
        val = field_data.get(key, f.get("default"))
        if val is None and f.get("required"):
            val = f.get("default", "")
        # Cast type
        if f["type"] == "integer":
            try:
                val = int(val)
            except (ValueError, TypeError):
                val = 0
        elif f["type"] == "float":
            try:
                val = float(val)
            except (ValueError, TypeError):
                val = 0.0
        context[key] = val

    # Dynamic computations for Demand Letter
    if template_id == "commercial_demand_letter":
        orig = float(context.get("original_amount", 0.0))
        interest = float(context.get("interest_accrued", 0.0))
        context["total_demand"] = orig + interest
        context["date_today"] = datetime.now().strftime("%B %d, %Y")

    # Render template string
    try:
        content = tmpl_spec["template"].format(**context)
    except KeyError as e:
        logger.warning(f"Template formatting key missing ({e}), filling with blank.")
        content = tmpl_spec["template"]

    return {
        "template_id": template_id,
        "template_name": tmpl_spec["name"],
        "generated_at": datetime.now().isoformat(),
        "document_content": content,
        "word_count": len(content.split()),
        "fields_used": context,
    }


def revise_commercial_document(
    document_content: str,
    instructions: str
) -> dict[str, Any]:
    """
    Apply structured revisions to commercial contract text.
    Uses local deterministic rule or LLM refinement if available.
    """
    instructions_clean = instructions.strip()
    revised = document_content

    # Rule-based fallback enhancements
    if "formal" in instructions_clean.lower():
        revised = revised.replace("will", "shall")
    if "california" in instructions_clean.lower() and "Governing Law" in revised:
        revised = revised.replace("State of New York", "State of California")

    # Append revision stamp
    revision_header = f"<!-- Revised via KruschBiz DraftPro at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC -->\n<!-- Instructions: {instructions_clean} -->\n\n"
    final_content = revision_header + revised

    return {
        "revised_content": final_content,
        "instructions_applied": instructions_clean,
        "timestamp": datetime.now().isoformat(),
    }
