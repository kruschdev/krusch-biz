"""
src/backend/business_router.py
==============================
FastAPI router for KruschBiz Business Operations & Commercial Utilities.
Features:
  - Contract Portfolio & Expiration Lifecycle alerts
  - Invoicing & Accounts Receivable tracking with aging calculations
  - Document OCR & Invoice Extraction
  - Commercial DraftPro document generation and revision
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .business_ocr import parse_business_document
from .business_templates import (
    generate_commercial_document,
    get_commercial_template,
    list_commercial_templates,
    revise_commercial_document,
)
from .db import (
    ContractPortfolio,
    Invoice,
    get_db,
)

logger = logging.getLogger("kruschbiz.business_api")

router = APIRouter()


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS
# ---------------------------------------------------------------------------

class ContractCreateRequest(BaseModel):
    contract_name: str = Field(..., min_length=2, max_length=255)
    vendor: str = Field(..., min_length=2, max_length=255)
    contract_type: str | None = Field(default="Vendor MSA")
    start_date: str | None = None  # YYYY-MM-DD
    expiration_date: str | None = None  # YYYY-MM-DD
    value: float | None = None
    auto_renew: bool = False
    reminder_days: str = "30,60,90"
    document_link: str | None = None
    notes: str | None = None
    agreement_id: int | None = None
    tenant_id: str = "org_default"


class ContractUpdateRequest(BaseModel):
    contract_name: str | None = None
    vendor: str | None = None
    contract_type: str | None = None
    expiration_date: str | None = None
    value: float | None = None
    auto_renew: bool | None = None
    status: str | None = None
    document_link: str | None = None
    notes: str | None = None


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    agreement_id: int | None
    contract_name: str
    vendor: str
    contract_type: str | None
    start_date: datetime | None
    expiration_date: datetime | None
    value: float | None
    auto_renew: bool
    reminder_days: str | None
    status: str
    document_link: str | None
    notes: str | None
    created_at: datetime | None
    days_until_expiration: int | None = None


class InvoiceItem(BaseModel):
    description: str
    quantity: float = 1.0
    rate: float = 0.0
    amount: float = 0.0


class InvoiceCreateRequest(BaseModel):
    invoice_number: str = Field(..., min_length=2, max_length=100)
    client_name: str = Field(..., min_length=2, max_length=255)
    client_email: str | None = None
    line_items: list[InvoiceItem] = Field(default_factory=list)
    tax_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    invoice_date: str | None = None  # YYYY-MM-DD
    due_date: str | None = None  # YYYY-MM-DD
    notes: str | None = None
    deal_id: int | None = None
    tenant_id: str = "org_default"


class InvoiceStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(draft|sent|paid|overdue|cancelled)$")


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    deal_id: int | None
    invoice_number: str
    client_name: str
    client_email: str | None
    line_items: Any
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    status: str
    invoice_date: datetime | None
    due_date: datetime | None
    sent_date: datetime | None
    paid_date: datetime | None
    notes: str | None
    created_at: datetime | None
    is_overdue: bool = False


class TemplateGenerateRequest(BaseModel):
    field_data: dict[str, Any] = Field(default_factory=dict)
    enhance_with_llm: bool = False


class TemplateReviseRequest(BaseModel):
    document_content: str = Field(..., min_length=10)
    instructions: str = Field(..., min_length=3)


# ---------------------------------------------------------------------------
# CONTRACT PORTFOLIO ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
def register_vendor_contract(req: ContractCreateRequest, db: Session = Depends(get_db)):
    """Register a new commercial vendor contract in the corporate portfolio."""
    start_dt = None
    exp_dt = None
    if req.start_date:
        try:
            start_dt = datetime.fromisoformat(req.start_date)
        except ValueError:
            pass
    if req.expiration_date:
        try:
            exp_dt = datetime.fromisoformat(req.expiration_date)
        except ValueError:
            pass

    contract = ContractPortfolio(
        tenant_id=req.tenant_id,
        agreement_id=req.agreement_id,
        contract_name=req.contract_name,
        vendor=req.vendor,
        contract_type=req.contract_type,
        start_date=start_dt,
        expiration_date=exp_dt,
        value=req.value,
        auto_renew=req.auto_renew,
        reminder_days=req.reminder_days,
        status="active",
        document_link=req.document_link,
        notes=req.notes,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    logger.info(f"Registered vendor contract '{contract.contract_name}' (ID {contract.id}) for vendor '{contract.vendor}'.")

    # Compute days until expiration
    days_left = None
    if contract.expiration_date:
        exp_naive = contract.expiration_date.replace(tzinfo=None)
        now_naive = datetime.now()
        days_left = (exp_naive - now_naive).days

    resp = ContractResponse.model_validate(contract)
    resp.days_until_expiration = days_left
    return resp


@router.get("/contracts", response_model=list[ContractResponse])
def list_contracts(
    status_filter: str | None = Query(None, description="Filter by status (active, expiring_soon, expired, renewed, terminated)"),
    vendor: str | None = Query(None, description="Filter by vendor name"),
    tenant_id: str = Query("org_default"),
    db: Session = Depends(get_db),
):
    """Enumerate vendor contracts in the portfolio with expiration status indicators."""
    query = db.query(ContractPortfolio).filter(ContractPortfolio.tenant_id == tenant_id)
    if status_filter:
        query = query.filter(ContractPortfolio.status == status_filter)
    if vendor:
        query = query.filter(ContractPortfolio.vendor.ilike(f"%{vendor}%"))

    contracts = query.order_by(ContractPortfolio.expiration_date.asc().nullslast()).all()
    results = []
    now_naive = datetime.now()

    for c in contracts:
        days_left = None
        if c.expiration_date:
            exp_naive = c.expiration_date.replace(tzinfo=None)
            days_left = (exp_naive - now_naive).days
            # Auto-update status if expired or expiring soon
            if days_left < 0 and c.status == "active":
                c.status = "expired"
                db.commit()
            elif 0 <= days_left <= 30 and c.status == "active":
                c.status = "expiring_soon"
                db.commit()

        item = ContractResponse.model_validate(c)
        item.days_until_expiration = days_left
        results.append(item)

    return results


@router.get("/contracts/expiring", response_model=list[ContractResponse])
def get_expiring_contracts(
    within_days: int = Query(60, ge=1, le=365, description="Lookahead window in days"),
    tenant_id: str = Query("org_default"),
    db: Session = Depends(get_db),
):
    """Enumerate contracts expiring within the specified lookahead window."""
    now = datetime.now()
    threshold = now + timedelta(days=within_days)

    contracts = db.query(ContractPortfolio).filter(
        ContractPortfolio.tenant_id == tenant_id,
        ContractPortfolio.status.in_(["active", "expiring_soon"]),
        ContractPortfolio.expiration_date.isnot(None),
        ContractPortfolio.expiration_date <= threshold,
    ).order_by(ContractPortfolio.expiration_date.asc()).all()

    results = []
    for c in contracts:
        exp_naive = c.expiration_date.replace(tzinfo=None)
        days_left = (exp_naive - now).days
        item = ContractResponse.model_validate(c)
        item.days_until_expiration = days_left
        results.append(item)

    return results


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
def get_contract_detail(contract_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a single vendor contract."""
    contract = db.query(ContractPortfolio).filter(ContractPortfolio.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found in portfolio.")

    days_left = None
    if contract.expiration_date:
        days_left = (contract.expiration_date.replace(tzinfo=None) - datetime.now()).days

    resp = ContractResponse.model_validate(contract)
    resp.days_until_expiration = days_left
    return resp


@router.patch("/contracts/{contract_id}", response_model=ContractResponse)
def update_contract(contract_id: int, req: ContractUpdateRequest, db: Session = Depends(get_db)):
    """Update contract parameters, renewal dates, or lifecycle status."""
    contract = db.query(ContractPortfolio).filter(ContractPortfolio.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found in portfolio.")

    if req.contract_name is not None:
        contract.contract_name = req.contract_name
    if req.vendor is not None:
        contract.vendor = req.vendor
    if req.contract_type is not None:
        contract.contract_type = req.contract_type
    if req.value is not None:
        contract.value = req.value
    if req.auto_renew is not None:
        contract.auto_renew = req.auto_renew
    if req.status is not None:
        contract.status = req.status
    if req.document_link is not None:
        contract.document_link = req.document_link
    if req.notes is not None:
        contract.notes = req.notes
    if req.expiration_date is not None:
        try:
            contract.expiration_date = datetime.fromisoformat(req.expiration_date)
        except ValueError:
            pass

    db.commit()
    db.refresh(contract)

    days_left = None
    if contract.expiration_date:
        days_left = (contract.expiration_date.replace(tzinfo=None) - datetime.now()).days

    resp = ContractResponse.model_validate(contract)
    resp.days_until_expiration = days_left
    return resp


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_200_OK)
def delete_contract(contract_id: int, db: Session = Depends(get_db)):
    """Remove a contract record from the portfolio."""
    contract = db.query(ContractPortfolio).filter(ContractPortfolio.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found.")

    db.delete(contract)
    db.commit()
    return {"status": "success", "message": f"Contract {contract_id} removed from portfolio."}


# ---------------------------------------------------------------------------
# INVOICING & ACCOUNTS RECEIVABLE ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(req: InvoiceCreateRequest, db: Session = Depends(get_db)):
    """Create a new commercial invoice with automated subtotal and tax calculation."""
    # Compute subtotal from line items
    subtotal = 0.0
    items_dicts = []
    for item in req.line_items:
        amt = round(item.quantity * item.rate, 2)
        items_dicts.append({
            "description": item.description,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amt,
        })
        subtotal += amt

    subtotal = round(subtotal, 2)
    tax_amount = round(subtotal * req.tax_rate, 2)
    total = round(subtotal + tax_amount, 2)

    inv_dt = None
    due_dt = None
    if req.invoice_date:
        try:
            inv_dt = datetime.fromisoformat(req.invoice_date)
        except ValueError:
            pass
    if req.due_date:
        try:
            due_dt = datetime.fromisoformat(req.due_date)
        except ValueError:
            pass
    if not inv_dt:
        inv_dt = datetime.now()

    invoice = Invoice(
        tenant_id=req.tenant_id,
        deal_id=req.deal_id,
        invoice_number=req.invoice_number,
        client_name=req.client_name,
        client_email=req.client_email,
        line_items=items_dicts,
        subtotal=subtotal,
        tax_rate=req.tax_rate,
        tax_amount=tax_amount,
        total=total,
        status="draft",
        invoice_date=inv_dt,
        due_date=due_dt,
        notes=req.notes,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    logger.info(f"Created invoice {invoice.invoice_number} (Total: ${invoice.total:,.2f}) for client {invoice.client_name}.")

    return InvoiceResponse.model_validate(invoice)


@router.get("/invoices", response_model=list[InvoiceResponse])
def list_invoices(
    status_filter: str | None = Query(None, description="Filter by status (draft, sent, paid, overdue, cancelled)"),
    client_name: str | None = Query(None, description="Filter by client name"),
    tenant_id: str = Query("org_default"),
    db: Session = Depends(get_db),
):
    """Enumerate invoices with overdue verification."""
    query = db.query(Invoice).filter(Invoice.tenant_id == tenant_id)
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if client_name:
        query = query.filter(Invoice.client_name.ilike(f"%{client_name}%"))

    invoices = query.order_by(Invoice.invoice_date.desc().nullslast()).all()
    results = []
    now_naive = datetime.now()

    for inv in invoices:
        is_od = False
        if inv.due_date:
            due_naive = inv.due_date.replace(tzinfo=None)
            if due_naive < now_naive and inv.status in ["draft", "sent"]:
                is_od = True
                inv.status = "overdue"
                db.commit()
            elif inv.status == "overdue":
                is_od = True

        item = InvoiceResponse.model_validate(inv)
        item.is_overdue = is_od
        results.append(item)

    return results


@router.get("/invoices/outstanding")
def get_outstanding_receivables(
    tenant_id: str = Query("org_default"),
    db: Session = Depends(get_db),
):
    """
    Accounts receivable summary including aging buckets (0-30, 31-60, 60+ days)
    and liquidity analytics.
    """
    invoices = db.query(Invoice).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.status != "cancelled"
    ).all()

    now = datetime.now()
    total_invoiced = 0.0
    total_paid = 0.0
    total_outstanding = 0.0
    total_overdue = 0.0

    bucket_0_30 = 0.0
    bucket_31_60 = 0.0
    bucket_60_plus = 0.0

    counts = {"draft": 0, "sent": 0, "paid": 0, "overdue": 0, "cancelled": 0}

    for inv in invoices:
        total_invoiced += inv.total
        counts[inv.status] = counts.get(inv.status, 0) + 1

        if inv.status == "paid":
            total_paid += inv.total
        elif inv.status in ["draft", "sent", "overdue"]:
            total_outstanding += inv.total
            days_past = 0
            if inv.due_date:
                days_past = (now - inv.due_date.replace(tzinfo=None)).days

            if days_past > 0:
                total_overdue += inv.total
                if days_past <= 30:
                    bucket_0_30 += inv.total
                elif days_past <= 60:
                    bucket_31_60 += inv.total
                else:
                    bucket_60_plus += inv.total
            else:
                bucket_0_30 += inv.total

    return {
        "tenant_id": tenant_id,
        "metrics": {
            "total_invoiced": round(total_invoiced, 2),
            "total_paid": round(total_paid, 2),
            "total_outstanding": round(total_outstanding, 2),
            "total_overdue": round(total_overdue, 2),
            "collection_rate_pct": round((total_paid / total_invoiced * 100.0), 1) if total_invoiced > 0 else 0.0,
        },
        "aging_buckets": {
            "current_and_0_30_days": round(bucket_0_30, 2),
            "past_due_31_60_days": round(bucket_31_60, 2),
            "past_due_60_plus_days": round(bucket_60_plus, 2),
        },
        "status_counts": counts,
    }


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a single invoice."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return InvoiceResponse.model_validate(inv)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceResponse)
def update_invoice_status(invoice_id: int, req: InvoiceStatusUpdate, db: Session = Depends(get_db)):
    """Transition invoice lifecycle status (draft -> sent -> paid / overdue / cancelled)."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    old_status = inv.status
    inv.status = req.status
    if req.status == "sent" and not inv.sent_date:
        inv.sent_date = datetime.now()
    elif req.status == "paid":
        inv.paid_date = datetime.now()

    db.commit()
    db.refresh(inv)
    logger.info(f"Invoice #{inv.invoice_number} transitioned status: {old_status} -> {inv.status}.")
    return InvoiceResponse.model_validate(inv)


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_200_OK)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Remove a draft or cancelled invoice."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if inv.status == "paid":
        raise HTTPException(status_code=400, detail="Cannot delete a paid invoice. Archive or mark cancelled.")

    db.delete(inv)
    db.commit()
    return {"status": "success", "message": f"Invoice {invoice_id} deleted."}


# ---------------------------------------------------------------------------
# OCR & DOCUMENT INTELLIGENCE
# ---------------------------------------------------------------------------

@router.post("/ocr/parse")
async def ocr_parse_business_document(
    file: UploadFile = File(...),
    doc_type_hint: str = Query("auto", description="Hint: invoice, receipt, contract, auto")
):
    """
    Extract structured commercial metadata (vendor, line items, totals, dates, payment terms)
    from uploaded invoice, receipt, or agreement document.
    """
    content = await file.read()
    try:
        extracted = parse_business_document(content, file.filename or "uploaded_doc", doc_type_hint)
        return {
            "status": "success",
            "filename": file.filename,
            "data": extracted,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OCR parsing failed for {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OCR parsing failed: {str(e)}")


# ---------------------------------------------------------------------------
# COMMERCIAL TEMPLATES (DRAFTPRO)
# ---------------------------------------------------------------------------

@router.get("/templates")
def get_templates():
    """Enumerate available commercial document drafting templates."""
    return list_commercial_templates()


@router.get("/templates/{template_id}")
def get_template_detail(template_id: str):
    """Get field schema and description for a specific commercial template."""
    tmpl = get_commercial_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    return tmpl


@router.post("/templates/{template_id}/generate")
def generate_document_endpoint(template_id: str, req: TemplateGenerateRequest):
    """Generate a completed commercial contract draft from parameter inputs."""
    try:
        return generate_commercial_document(template_id, req.field_data, req.enhance_with_llm)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/templates/revise")
def revise_document_endpoint(req: TemplateReviseRequest):
    """Apply legal revisions and refinements to commercial agreement text."""
    return revise_commercial_document(req.document_content, req.instructions)
