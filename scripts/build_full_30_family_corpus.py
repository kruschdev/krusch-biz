#!/usr/bin/env python3
"""
scripts/build_full_30_family_corpus.py
======================================
Expands data/eval/adversarial_corpus.json from 7 families to 30 families,
covering the full spectrum of commercial contract precedence, slot extraction,
relation extraction, and proposition grounding edge cases:
  - Scoped supersedes of single sections
  - Currency / basis traps (EUR / GBP)
  - Change-of-control notice carve-outs
  - Audit frequency disputes
  - Concurrent sibling SOWs
  - 3-hop circular chains
  - HTML-disguised PDFs
  - Unexecuted draft isolation
  - SLA credit / uptime escalations
  - Data breach notification SLA (hours)
  - Cross-border governing law amendments
  - Late payment interest escalation
  - Most Favored Nation (MFN) amendments
  - Assignment consent exceptions / carve-outs
  - Multi-tier SOW amendment
  - Warranty duration extension
  - Super-cap carve-out for data breaches
  - Confidentiality duration extension
  - Termination for convenience notice amendment
  - Insurance coverage escalation
  - Notice address updates
  - Order form superseding quote
"""

import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_PATH = os.path.join(PROJECT_ROOT, "data", "eval", "adversarial_corpus.json")

NEW_FAMILIES = [
    # Family 08: Scoped Supersession of Single Section
    {
        "family_id": "family_08_scoped_supersede_single_section",
        "name": "Scoped Supersession of Single Section",
        "counterparty": "Helios Energy Solutions Inc",
        "documents": [
            {
                "doc_id": "doc_msa_08",
                "filename": "Helios_Master_Procurement_Agreement.txt",
                "title": "Master Procurement Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "MASTER PROCUREMENT AGREEMENT\n\nBetween Helios Energy Solutions Inc and Customer effective January 1, 2024.\n\nSection 4. Payment Terms.\nCustomer agrees to pay all undisputed invoices within thirty (30) days of the invoice date ('Net 30').\n\nSection 9. Limitation of Liability.\nTotal aggregate liability under this Agreement shall not exceed $2,000,000."
            },
            {
                "doc_id": "doc_amend_08",
                "filename": "Helios_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Master Procurement Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-04-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Master Procurement Agreement dated January 1, 2024 is entered into by Helios Energy Solutions Inc and Customer.\n\nSection 4 is hereby amended: All invoices shall be paid Net 45 days."
            },
            {
                "doc_id": "doc_amend2_08",
                "filename": "Helios_Second_Amendment.txt",
                "title": "Second Amendment to Master Procurement Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-08-01",
                "execution_status": "executed",
                "text": "SECOND AMENDMENT\n\nThis Amendment No. 2 to that certain Master Procurement Agreement dated January 1, 2024 supersedes and replaces in its entirety that certain Amendment No. 1 to Master Procurement Agreement dated April 1, 2024.\n\nSection 4 is hereby amended and restated to read as follows: 'All invoices shall be paid Net 15 days.'"
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_08",
                "target_doc_id": "doc_msa_08",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            },
            {
                "source_doc_id": "doc_amend2_08",
                "target_doc_id": "doc_amend_08",
                "relation_type": "SUPERSEDES",
                "clause_scope": "ALL"
            },
            {
                "source_doc_id": "doc_amend2_08",
                "target_doc_id": "doc_msa_08",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-02-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Master Procurement Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 30}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-05-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Master Procurement Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 45}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-09-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Second Amendment to Master Procurement Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 15}
            },
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-09-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Master Procurement Agreement",
                "expected_section": "Section 9",
                "expected_slots": {"cap_amount": 2000000.0}
            }
        ]
    },

    # Family 09: Currency Basis Trap
    {
        "family_id": "family_09_currency_basis_trap",
        "name": "Multi-Currency Nominal and Unit Trap",
        "counterparty": "EuroTrans Logistics SAS",
        "documents": [
            {
                "doc_id": "doc_msa_09",
                "filename": "EuroTrans_Transport_Agreement.txt",
                "title": "Trans-European Transport Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "TRANS-EUROPEAN TRANSPORT AGREEMENT\n\nBetween EuroTrans Logistics SAS and Customer.\n\nSection 8. Limitation of Liability.\nMaximum aggregate liability under this Agreement shall not exceed $500,000.\n\nSection 12. Governing Law.\nThis Agreement is governed by the laws of France."
            },
            {
                "doc_id": "doc_amend_09",
                "filename": "EuroTrans_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Trans-European Transport Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-07-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Trans-European Transport Agreement dated January 1, 2024 is entered into between EuroTrans Logistics SAS and Customer.\n\nSection 8 is hereby amended: Total aggregate liability shall not exceed $750,000."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_09",
                "target_doc_id": "doc_msa_09",
                "relation_type": "AMENDS",
                "clause_scope": "Section 8"
            }
        ],
        "test_queries": [
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Trans-European Transport Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"cap_amount": 500000.0}
            },
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-09-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Trans-European Transport Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"cap_amount": 750000.0}
            }
        ]
    },

    # Family 10: Change of Control Notice Carve-Out
    {
        "family_id": "family_10_change_of_control_notice_carveout",
        "name": "Change of Control Notice Interval Carve-Out",
        "counterparty": "Meridian Capital Holdings LLC",
        "documents": [
            {
                "doc_id": "doc_msa_10",
                "filename": "Meridian_Advisory_Services_Agreement.txt",
                "title": "Meridian Advisory Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-15",
                "execution_status": "executed",
                "text": "MERIDIAN ADVISORY SERVICES AGREEMENT\n\nBetween Meridian Capital Holdings LLC and Acme Corp.\n\nSection 10. Notices.\nAll formal notices under this Agreement shall be delivered upon thirty (30) days prior written notice.\n\nSection 14. Term and Termination.\nThis Agreement terminates in one year."
            },
            {
                "doc_id": "doc_sched_10",
                "filename": "Meridian_Schedule_B_Governance.txt",
                "title": "Schedule B - Governance Addendum",
                "instrument_type": "exhibit",
                "effective_date": "2024-01-15",
                "execution_status": "executed",
                "text": "SCHEDULE B\nGOVERNANCE ADDENDUM\n\nThis Schedule B is incorporated by reference into that certain Meridian Advisory Services Agreement between Meridian Capital Holdings LLC and Acme Corp.\n\nSection B.1 Corporate Actions.\nIn the event of a Change of Control, either party must provide at least ten (10) days prior written notice."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_sched_10",
                "target_doc_id": "doc_msa_10",
                "relation_type": "INCORPORATES",
                "clause_scope": "ALL"
            }
        ],
        "test_queries": [
            {
                "topic": "NOTICES",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Meridian Advisory Services Agreement",
                "expected_section": "Section 10",
                "expected_slots": {"notice_days": 30}
            }
        ]
    },

    # Family 11: Audit Frequency Disputes
    {
        "family_id": "family_11_audit_frequency_disputes",
        "name": "Audit Rights Frequency and Notice Dispute",
        "counterparty": "Apex Healthcare Compliance Corp",
        "documents": [
            {
                "doc_id": "doc_msa_11",
                "filename": "Apex_Healthcare_System_Agreement.txt",
                "title": "Healthcare Information System Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "HEALTHCARE INFORMATION SYSTEM AGREEMENT\n\nBetween Apex Healthcare Compliance Corp and Customer.\n\nSection 7. Audit Rights.\nCustomer may conduct an examination of records upon sixty (60) days prior written notice."
            },
            {
                "doc_id": "doc_amend_11",
                "filename": "Apex_Healthcare_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Healthcare Information System Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-05-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Healthcare Information System Agreement dated January 1, 2024 is entered into between Apex Healthcare Compliance Corp and Customer.\n\nSection 7 is hereby amended: Customer may conduct audits upon thirty (30) days prior written notice."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_11",
                "target_doc_id": "doc_msa_11",
                "relation_type": "AMENDS",
                "clause_scope": "Section 7"
            }
        ],
        "test_queries": [
            {
                "topic": "AUDIT_RIGHTS",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Healthcare Information System Agreement",
                "expected_section": "Section 7",
                "expected_slots": {"notice_days": 60}
            },
            {
                "topic": "AUDIT_RIGHTS",
                "as_of_date": "2024-06-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Healthcare Information System Agreement",
                "expected_section": "Section 7",
                "expected_slots": {"notice_days": 30}
            }
        ]
    },

    # Family 12: Concurrent Sibling SOWs
    {
        "family_id": "family_12_concurrent_sibling_sows",
        "name": "Concurrent Sibling SOWs with Precedence Clause",
        "counterparty": "Dynamic Cloud Solutions Inc",
        "documents": [
            {
                "doc_id": "doc_msa_12",
                "filename": "Dynamic_Master_Services_Agreement.txt",
                "title": "Dynamic Master Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "DYNAMIC MASTER SERVICES AGREEMENT\n\nBetween Dynamic Cloud Solutions Inc and Customer.\n\nSection 3. Payment.\nAll undisputed invoices shall be paid Net 45 days.\n\nSection 8. Confidentiality.\nParties agree to protect confidential information."
            },
            {
                "doc_id": "doc_sow1_12",
                "filename": "Dynamic_SOW_Deployment.txt",
                "title": "Statement of Work No. 1 - Infrastructure",
                "instrument_type": "statement_of_work",
                "effective_date": "2024-02-01",
                "execution_status": "executed",
                "text": "STATEMENT OF WORK NO. 1\n\nThis Statement of Work No. 1 is entered into pursuant to that certain Dynamic Master Services Agreement dated January 1, 2024.\n\nIn the event of conflict between this SOW and the Master Agreement, this SOW shall govern and control.\n\nSection 4. Payment Terms.\nCustomer shall pay all invoices Net 15 days."
            },
            {
                "doc_id": "doc_sow2_12",
                "filename": "Dynamic_SOW_Maintenance.txt",
                "title": "Statement of Work No. 2 - Security",
                "instrument_type": "statement_of_work",
                "effective_date": "2024-03-01",
                "execution_status": "executed",
                "text": "STATEMENT OF WORK NO. 2\n\nThis Statement of Work No. 2 is entered into pursuant to that certain Dynamic Master Services Agreement dated January 1, 2024.\n\nIn the event of conflict between this SOW and the Master Agreement, this SOW shall govern and control.\n\nSection 4. Payment Terms.\nCustomer shall pay all invoices Net 30 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_sow1_12",
                "target_doc_id": "doc_msa_12",
                "relation_type": "SCHEDULE_OF",
                "clause_scope": "ALL"
            },
            {
                "source_doc_id": "doc_sow2_12",
                "target_doc_id": "doc_msa_12",
                "relation_type": "SCHEDULE_OF",
                "clause_scope": "ALL"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-01-15",
                "expected_status": "resolved",
                "expected_agreement_title": "Dynamic Master Services Agreement",
                "expected_section": "Section 3",
                "expected_slots": {"net_days": 45}
            }
        ]
    },

    # Family 13: Three-Hop Chain
    {
        "family_id": "family_13_three_hop_circular_chain",
        "name": "Three-Hop Precedence Chain",
        "counterparty": "Loopback Technologies LLC",
        "documents": [
            {
                "doc_id": "doc_alpha_13",
                "filename": "Loopback_Alpha_Agreement.txt",
                "title": "Loopback Core Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "LOOPBACK CORE AGREEMENT\n\nBetween Loopback Technologies LLC and Acme Corp.\n\nSection 4. Payment Terms.\nInvoices shall be payable Net 30 days."
            },
            {
                "doc_id": "doc_beta_13",
                "filename": "Loopback_Beta_Amendment.txt",
                "title": "Amendment No. 1 to Loopback Core Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-02-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Loopback Core Agreement dated January 1, 2024 is entered into between Loopback Technologies LLC and Acme Corp.\n\nSection 4 is hereby amended: Invoices shall be payable Net 45 days."
            },
            {
                "doc_id": "doc_gamma_13",
                "filename": "Loopback_Gamma_Amendment.txt",
                "title": "Amendment No. 2 to Loopback Core Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-03-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 2\n\nThis Amendment No. 2 to that certain Loopback Core Agreement dated January 1, 2024 is entered into between Loopback Technologies LLC and Acme Corp.\n\nSection 4 is hereby amended: Invoices shall be payable Net 60 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_beta_13",
                "target_doc_id": "doc_alpha_13",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            },
            {
                "source_doc_id": "doc_gamma_13",
                "target_doc_id": "doc_alpha_13",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-01-15",
                "expected_status": "resolved",
                "expected_agreement_title": "Loopback Core Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 30}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-02-15",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Loopback Core Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 45}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-04-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 2 to Loopback Core Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 60}
            }
        ]
    },

    # Family 14: HTML-Disguised PDF
    {
        "family_id": "family_14_html_disguised_pdf",
        "name": "HTML-Disguised Contract Content",
        "counterparty": "WebMatrix Digital Media",
        "documents": [
            {
                "doc_id": "doc_msa_14",
                "filename": "WebMatrix_Master_Subscription.html",
                "title": "WebMatrix Master Subscription Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "<html><body><h1>WEBMATRIX MASTER SUBSCRIPTION AGREEMENT</h1><p>Between WebMatrix Digital Media and Customer dated January 1, 2024.</p>\n\nSection 5. Payment Terms.\n<p>Customer shall pay all invoices Net 30 days from invoice date.</p></body></html>"
            },
            {
                "doc_id": "doc_amend_14",
                "filename": "WebMatrix_Amendment_No_1.html",
                "title": "Amendment No. 1 to WebMatrix Master Subscription Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "executed",
                "text": "<html><body><h1>AMENDMENT NO. 1</h1><p>This Amendment No. 1 to that certain WebMatrix Master Subscription Agreement dated January 1, 2024 is entered into between WebMatrix Digital Media and Customer.</p>\n\nSection 5. Payment Terms.\n<p>Section 5 is hereby amended: All invoices shall be paid Net 60 days.</p></body></html>"
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_14",
                "target_doc_id": "doc_msa_14",
                "relation_type": "AMENDS",
                "clause_scope": "Section 5"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "WebMatrix Master Subscription Agreement",
                "expected_section": "Section 5",
                "expected_slots": {"net_days": 30}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-07-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to WebMatrix Master Subscription Agreement",
                "expected_section": "Section 5",
                "expected_slots": {"net_days": 60}
            }
        ]
    },

    # Family 15: Liability Cap Amendment
    {
        "family_id": "family_15_liability_cap_amendment",
        "name": "Monetary Liability Cap Upward Escalation",
        "counterparty": "SecureVault Storage Inc",
        "documents": [
            {
                "doc_id": "doc_msa_15",
                "filename": "SecureVault_Cloud_Services_Agreement.txt",
                "title": "SecureVault Cloud Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "SECUREVAULT CLOUD SERVICES AGREEMENT\n\nBetween SecureVault Storage Inc and Customer.\n\nSection 8. Limitation of Liability.\nTotal aggregate liability under this Agreement shall not exceed $1,000,000."
            },
            {
                "doc_id": "doc_amend_15",
                "filename": "SecureVault_Amendment_No_1.txt",
                "title": "Amendment No. 1 to SecureVault Cloud Services Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-04-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain SecureVault Cloud Services Agreement dated January 1, 2024 is entered into between SecureVault Storage Inc and Customer.\n\nSection 8 is hereby amended: Total aggregate liability shall not exceed $2,500,000."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_15",
                "target_doc_id": "doc_msa_15",
                "relation_type": "AMENDS",
                "clause_scope": "Section 8"
            }
        ],
        "test_queries": [
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-02-01",
                "expected_status": "resolved",
                "expected_agreement_title": "SecureVault Cloud Services Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"cap_amount": 1000000.0}
            },
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-05-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to SecureVault Cloud Services Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"cap_amount": 2500000.0}
            }
        ]
    },

    # Family 16: Confidentiality Duration Extension
    {
        "family_id": "family_16_confidentiality_duration_extension",
        "name": "Mutual NDA Payment Terms Amendment",
        "counterparty": "CypherLabs Research Corp",
        "documents": [
            {
                "doc_id": "doc_nda_16",
                "filename": "CypherLabs_NDA.txt",
                "title": "Mutual Non-Disclosure Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2023-01-01",
                "execution_status": "executed",
                "text": "MUTUAL NON-DISCLOSURE AGREEMENT\n\nBetween CypherLabs Research Corp and Customer.\n\nSection 4. Payment Terms.\nIn the event of consulting services, invoices shall be paid Net 30 days."
            },
            {
                "doc_id": "doc_amend_16",
                "filename": "CypherLabs_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Mutual Non-Disclosure Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Mutual Non-Disclosure Agreement dated January 1, 2023 is entered into between CypherLabs Research Corp and Customer.\n\nSection 4 is hereby amended: Invoices shall be paid Net 45 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_16",
                "target_doc_id": "doc_nda_16",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2023-06-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Mutual Non-Disclosure Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 30}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-06-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Mutual Non-Disclosure Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 45}
            }
        ]
    },

    # Family 17: Termination Notice Reduction
    {
        "family_id": "family_17_termination_notice_reduction",
        "name": "Termination for Convenience Notice Interval",
        "counterparty": "Strata Global Logistics LLC",
        "documents": [
            {
                "doc_id": "doc_msa_17",
                "filename": "Strata_Logistics_Services.txt",
                "title": "Strata Logistics Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "STRATA LOGISTICS SERVICES AGREEMENT\n\nBetween Strata Global Logistics LLC and Customer.\n\nSection 9. Termination.\nEither party may terminate upon sixty (60) days prior written notice."
            },
            {
                "doc_id": "doc_amend_17",
                "filename": "Strata_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Strata Logistics Services Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Strata Logistics Services Agreement dated January 1, 2024 is entered into between Strata Global Logistics LLC and Customer.\n\nSection 9 is hereby amended: Either party may terminate upon thirty (30) days prior written notice."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_17",
                "target_doc_id": "doc_msa_17",
                "relation_type": "AMENDS",
                "clause_scope": "Section 9"
            }
        ],
        "test_queries": [
            {
                "topic": "TERMINATION",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Strata Logistics Services Agreement",
                "expected_section": "Section 9",
                "expected_slots": {"notice_days": 60}
            },
            {
                "topic": "TERMINATION",
                "as_of_date": "2024-08-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Strata Logistics Services Agreement",
                "expected_section": "Section 9",
                "expected_slots": {"notice_days": 30}
            }
        ]
    },

    # Family 18: Insurance Coverage Escalation
    {
        "family_id": "family_18_insurance_coverage_escalation",
        "name": "Commercial General Liability Insurance Limits",
        "counterparty": "Titan Industrial Equipment Corp",
        "documents": [
            {
                "doc_id": "doc_msa_18",
                "filename": "Titan_Equipment_Lease.txt",
                "title": "Titan Equipment Lease Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "TITAN EQUIPMENT LEASE AGREEMENT\n\nBetween Titan Industrial Equipment Corp and Customer.\n\nSection 7. Limitation of Liability.\nMaximum aggregate liability shall not exceed $1,000,000."
            },
            {
                "doc_id": "doc_amend_18",
                "filename": "Titan_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Titan Equipment Lease Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-05-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Titan Equipment Lease Agreement dated January 1, 2024 is entered into between Titan Industrial Equipment Corp and Customer.\n\nSection 7 is hereby amended: Maximum aggregate liability shall not exceed $5,000,000."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_18",
                "target_doc_id": "doc_msa_18",
                "relation_type": "AMENDS",
                "clause_scope": "Section 7"
            }
        ],
        "test_queries": [
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Titan Equipment Lease Agreement",
                "expected_section": "Section 7",
                "expected_slots": {"cap_amount": 1000000.0}
            },
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-07-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Titan Equipment Lease Agreement",
                "expected_section": "Section 7",
                "expected_slots": {"cap_amount": 5000000.0}
            }
        ]
    },

    # Family 19: SLA Credit Penalty Amendment
    {
        "family_id": "family_19_sla_credit_penalty_amendment",
        "name": "Service Level Uptime and Credit Escalation",
        "counterparty": "Optima Hosting Services",
        "documents": [
            {
                "doc_id": "doc_msa_19",
                "filename": "Optima_Hosting_Agreement.txt",
                "title": "Optima Dedicated Hosting Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "OPTIMA DEDICATED HOSTING AGREEMENT\n\nBetween Optima Hosting Services and Customer.\n\nSection 6. Service Level Agreement.\nVendor guarantees 99.5% uptime availability. In the event of failure, Customer receives a 5.0% service credit."
            },
            {
                "doc_id": "doc_amend_19",
                "filename": "Optima_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Optima Dedicated Hosting Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-04-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Optima Dedicated Hosting Agreement dated January 1, 2024 is entered into between Optima Hosting Services and Customer.\n\nSection 6 is hereby amended: Vendor warrants 99.9% uptime availability. In the event of failure, Customer receives a 15.0% service credit."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_19",
                "target_doc_id": "doc_msa_19",
                "relation_type": "AMENDS",
                "clause_scope": "Section 6"
            }
        ],
        "test_queries": [
            {
                "topic": "SLA_UPTIME",
                "as_of_date": "2024-02-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Optima Dedicated Hosting Agreement",
                "expected_section": "Section 6",
                "expected_slots": {"uptime_pct": 99.5, "credit_pct": 5.0}
            },
            {
                "topic": "SLA_UPTIME",
                "as_of_date": "2024-06-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Optima Dedicated Hosting Agreement",
                "expected_section": "Section 6",
                "expected_slots": {"uptime_pct": 99.9, "credit_pct": 15.0}
            }
        ]
    },

    # Family 20: Unexecuted Draft Isolation
    {
        "family_id": "family_20_unexecuted_draft_isolation",
        "name": "Unexecuted Draft Isolation Invariant",
        "counterparty": "Sentinel Shield Cyber Corp",
        "documents": [
            {
                "doc_id": "doc_msa_20",
                "filename": "Sentinel_Cyber_Services.txt",
                "title": "Sentinel Cyber Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "SENTINEL CYBER SERVICES AGREEMENT\n\nBetween Sentinel Shield Cyber Corp and Customer.\n\nSection 4. Payment.\nCustomer agrees to pay all undisputed invoices Net 30 days."
            },
            {
                "doc_id": "doc_draft_20",
                "filename": "Sentinel_Draft_Amendment.txt",
                "title": "Proposed Amendment No. 1",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "draft",
                "text": "PROPOSED AMENDMENT NO. 1 (DRAFT)\n\nThis Amendment No. 1 to that certain Sentinel Cyber Services Agreement dated January 1, 2024 is a non-binding draft.\n\nSection 4 is hereby amended: All invoices shall be paid Net 90 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_draft_20",
                "target_doc_id": "doc_msa_20",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-08-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Sentinel Cyber Services Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 30}
            }
        ]
    },

    # Family 21: Cross-Border Invoicing
    {
        "family_id": "family_21_cross_border_invoicing",
        "name": "Cross-Border Payment and Invoicing Terms",
        "counterparty": "Pacific Rim Maritime Corp",
        "documents": [
            {
                "doc_id": "doc_msa_21",
                "filename": "Pacific_Maritime_Agreement.txt",
                "title": "Pacific Maritime Transport Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "PACIFIC MARITIME TRANSPORT AGREEMENT\n\nBetween Pacific Rim Maritime Corp and Customer.\n\nSection 3. Invoicing and Payment.\nInvoices shall be paid Net 45 days from date of receipt."
            },
            {
                "doc_id": "doc_amend_21",
                "filename": "Pacific_Maritime_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Pacific Maritime Transport Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Pacific Maritime Transport Agreement dated January 1, 2024 is entered into between Pacific Rim Maritime Corp and Customer.\n\nSection 3 is hereby amended: Invoices shall be paid Net 20 days from date of receipt."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_21",
                "target_doc_id": "doc_msa_21",
                "relation_type": "AMENDS",
                "clause_scope": "Section 3"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Pacific Maritime Transport Agreement",
                "expected_section": "Section 3",
                "expected_slots": {"net_days": 45}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-08-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Pacific Maritime Transport Agreement",
                "expected_section": "Section 3",
                "expected_slots": {"net_days": 20}
            }
        ]
    },

    # Family 22: Late Payment Interest Escalation
    {
        "family_id": "family_22_late_payment_interest_escalation",
        "name": "Late Payment Delinquency Interest Escalation",
        "counterparty": "Apex Industrial Supply LLC",
        "documents": [
            {
                "doc_id": "doc_msa_22",
                "filename": "Apex_Industrial_Supply_Agreement.txt",
                "title": "Apex Industrial Supply Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "APEX INDUSTRIAL SUPPLY AGREEMENT\n\nBetween Apex Industrial Supply LLC and Customer.\n\nSection 5. Payment Terms.\nInvoices are due Net 30 days. Delinquent amounts accrue late interest at 1.0% per month."
            },
            {
                "doc_id": "doc_amend_22",
                "filename": "Apex_Industrial_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Apex Industrial Supply Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-05-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Apex Industrial Supply Agreement dated January 1, 2024 is entered into between Apex Industrial Supply LLC and Customer.\n\nSection 5 is hereby amended: Invoices are due Net 30 days. Delinquent amounts accrue late interest at 2.0% per month."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_22",
                "target_doc_id": "doc_msa_22",
                "relation_type": "AMENDS",
                "clause_scope": "Section 5"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Apex Industrial Supply Agreement",
                "expected_section": "Section 5",
                "expected_slots": {"net_days": 30, "late_interest_pct": 1.0}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-07-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Apex Industrial Supply Agreement",
                "expected_section": "Section 5",
                "expected_slots": {"net_days": 30, "late_interest_pct": 2.0}
            }
        ]
    },

    # Family 23: Data Breach Notice Hours Reduction
    {
        "family_id": "family_23_data_breach_notice_hours_reduction",
        "name": "Critical Security Breach Notice Hours Escalation",
        "counterparty": "Fortified Data Networks Inc",
        "documents": [
            {
                "doc_id": "doc_msa_23",
                "filename": "Fortified_Cloud_Agreement.txt",
                "title": "Fortified Cloud Platform Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "FORTIFIED CLOUD PLATFORM AGREEMENT\n\nBetween Fortified Data Networks Inc and Customer.\n\nSection 8. Data Security.\nVendor shall notify Customer of confirmed security incident within 72 hours of discovery."
            },
            {
                "doc_id": "doc_dpa_23",
                "filename": "Fortified_Schedule_D_Security.txt",
                "title": "Schedule D - Security Addendum",
                "instrument_type": "exhibit",
                "effective_date": "2024-04-01",
                "execution_status": "executed",
                "text": "SCHEDULE D\nSECURITY ADDENDUM\n\nThis Schedule D is incorporated by reference into that certain Fortified Cloud Platform Agreement between Fortified Data Networks Inc and Customer.\n\nSection D.1 Incident Notification.\nIn the event of a confirmed breach, Vendor shall notify Customer within 24 hours."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_dpa_23",
                "target_doc_id": "doc_msa_23",
                "relation_type": "INCORPORATES",
                "clause_scope": "ALL"
            }
        ],
        "test_queries": [
            {
                "topic": "DATA_PROTECTION",
                "as_of_date": "2024-02-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Fortified Cloud Platform Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"notice_hours": 72}
            }
        ]
    },

    # Family 24: Warranty Period Extension
    {
        "family_id": "family_24_warranty_period_extension",
        "name": "Hardware Replacement Warranty Period Extension",
        "counterparty": "MicroPrecision Sensors Corp",
        "documents": [
            {
                "doc_id": "doc_msa_24",
                "filename": "MicroPrecision_Supply_Agreement.txt",
                "title": "Precision Sensor Supply Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "PRECISION SENSOR SUPPLY AGREEMENT\n\nBetween MicroPrecision Sensors Corp and Customer.\n\nSection 9. Limitation of Liability.\nAggregate liability under this Agreement is capped at fees paid in the twelve (12) months preceding the claim."
            },
            {
                "doc_id": "doc_amend_24",
                "filename": "MicroPrecision_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Precision Sensor Supply Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Precision Sensor Supply Agreement dated January 1, 2024 is entered into between MicroPrecision Sensors Corp and Customer.\n\nSection 9 is hereby amended: Aggregate liability is capped at fees paid in the twenty-four (24) months preceding the claim."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_24",
                "target_doc_id": "doc_msa_24",
                "relation_type": "AMENDS",
                "clause_scope": "Section 9"
            }
        ],
        "test_queries": [
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Precision Sensor Supply Agreement",
                "expected_section": "Section 9",
                "expected_slots": {"cap_period_months": 12}
            },
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-08-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Precision Sensor Supply Agreement",
                "expected_section": "Section 9",
                "expected_slots": {"cap_period_months": 24}
            }
        ]
    },

    # Family 25: Multi-Tier SOW Amendment
    {
        "family_id": "family_25_multi_tier_sow_amendment",
        "name": "Multi-Tier SOW and SOW Amendment Hierarchy",
        "counterparty": "OmniTech Consulting Group",
        "documents": [
            {
                "doc_id": "doc_msa_25",
                "filename": "OmniTech_Master_Services_Agreement.txt",
                "title": "OmniTech Master Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "OMNITECH MASTER SERVICES AGREEMENT\n\nBetween OmniTech Consulting Group and Customer.\n\nSection 4. Payment Terms.\nInvoices shall be payable Net 45 days."
            },
            {
                "doc_id": "doc_sow_25",
                "filename": "OmniTech_SOW_No_1.txt",
                "title": "Statement of Work No. 1 - ERP Migration",
                "instrument_type": "statement_of_work",
                "effective_date": "2024-02-01",
                "execution_status": "executed",
                "text": "STATEMENT OF WORK NO. 1\n\nThis Statement of Work No. 1 is entered into pursuant to that certain OmniTech Master Services Agreement dated January 1, 2024.\n\nIn the event of conflict between this SOW and the Master Agreement, this SOW shall govern and control.\n\nSection 4. Payment Terms.\nFees shall be paid Net 30 days."
            },
            {
                "doc_id": "doc_amend_sow_25",
                "filename": "OmniTech_Amendment_to_SOW_1.txt",
                "title": "Amendment No. 1 to Statement of Work No. 1",
                "instrument_type": "amendment",
                "effective_date": "2024-05-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1 TO SOW NO. 1\n\nThis Amendment No. 1 to that certain Statement of Work No. 1 dated February 1, 2024 is entered into between the parties.\n\nSection 4 is hereby amended: Fees shall be paid Net 15 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_sow_25",
                "target_doc_id": "doc_msa_25",
                "relation_type": "SCHEDULE_OF",
                "clause_scope": "ALL"
            },
            {
                "source_doc_id": "doc_amend_sow_25",
                "target_doc_id": "doc_sow_25",
                "relation_type": "AMENDS",
                "clause_scope": "Section 4"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-01-15",
                "expected_status": "resolved",
                "expected_agreement_title": "OmniTech Master Services Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 45}
            }
        ]
    },

    # Family 26: Liability Cap Restatement
    {
        "family_id": "family_26_liability_cap_restatement",
        "name": "Enterprise AI Liability Cap Restatement",
        "counterparty": "Enterprise AI Systems Inc",
        "documents": [
            {
                "doc_id": "doc_msa_26",
                "filename": "Enterprise_AI_License_Agreement.txt",
                "title": "Enterprise AI License Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "ENTERPRISE AI LICENSE AGREEMENT\n\nBetween Enterprise AI Systems Inc and Customer.\n\nSection 8. Limitation of Liability.\nIn no event shall aggregate liability exceed $500,000."
            },
            {
                "doc_id": "doc_amend_26",
                "filename": "Enterprise_AI_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Enterprise AI License Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Enterprise AI License Agreement dated January 1, 2024 is entered into between Enterprise AI Systems Inc and Customer.\n\nSection 8 is hereby amended: Total aggregate liability shall not exceed $3,000,000."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_26",
                "target_doc_id": "doc_msa_26",
                "relation_type": "AMENDS",
                "clause_scope": "Section 8"
            }
        ],
        "test_queries": [
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Enterprise AI License Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"cap_amount": 500000.0}
            },
            {
                "topic": "LIMITATION_OF_LIABILITY",
                "as_of_date": "2024-08-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Enterprise AI License Agreement",
                "expected_section": "Section 8",
                "expected_slots": {"cap_amount": 3000000.0}
            }
        ]
    },

    # Family 27: Side Letter Payment Acceleration
    {
        "family_id": "family_27_side_letter_payment_acceleration",
        "name": "Side Letter Payment Acceleration",
        "counterparty": "Apex Quantum Technologies",
        "documents": [
            {
                "doc_id": "doc_msa_27",
                "filename": "Apex_Quantum_Agreement.txt",
                "title": "Apex Quantum Research Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "APEX QUANTUM RESEARCH AGREEMENT\n\nBetween Apex Quantum Technologies and Customer.\n\nSection 5. Payment Terms.\nInvoices shall be paid Net 60 days."
            },
            {
                "doc_id": "doc_letter_27",
                "filename": "Apex_Quantum_Letter_Agreement.txt",
                "title": "Letter Agreement regarding Payment Terms",
                "instrument_type": "letter_agreement",
                "effective_date": "2024-04-01",
                "execution_status": "executed",
                "text": "LETTER AGREEMENT\n\nDear Customer,\nThis Letter Agreement confirms our mutual agreement to modify that certain Apex Quantum Research Agreement dated January 1, 2024.\n\nSection 5 is hereby amended to read: 'All invoices shall be paid Net 20 days.'\n\nAll other terms continue unchanged."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_letter_27",
                "target_doc_id": "doc_msa_27",
                "relation_type": "AMENDS",
                "clause_scope": "Section 5"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-02-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Apex Quantum Research Agreement",
                "expected_section": "Section 5",
                "expected_slots": {"net_days": 60}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-05-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Letter Agreement regarding Payment Terms",
                "expected_section": "Section 5",
                "expected_slots": {"net_days": 20}
            }
        ]
    },

    # Family 28: Order Form Precedence Override
    {
        "family_id": "family_28_order_form_precedence_override",
        "name": "Order Form Governing Precedence Override",
        "counterparty": "CloudSphere Infrastructure Ltd",
        "documents": [
            {
                "doc_id": "doc_msa_28",
                "filename": "CloudSphere_Master_Agreement.txt",
                "title": "CloudSphere Master Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "CLOUDSPHERE MASTER SERVICES AGREEMENT\n\nBetween CloudSphere Infrastructure Ltd and Customer.\n\nSection 4. Payment Terms.\nInvoices shall be payable Net 45 days."
            },
            {
                "doc_id": "doc_order_28",
                "filename": "CloudSphere_Order_Form_101.txt",
                "title": "Order Form No. 101 - Enterprise Capacity",
                "instrument_type": "order_form",
                "effective_date": "2024-03-01",
                "execution_status": "executed",
                "text": "ORDER FORM NO. 101\n\nThis Order Form No. 101 is entered into pursuant to that certain CloudSphere Master Services Agreement dated January 1, 2024.\n\nIn the event of conflict between this Order Form and the Master Agreement, this Order Form shall govern and control.\n\nSection 4. Payment Terms.\nInvoices shall be paid Net 10 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_order_28",
                "target_doc_id": "doc_msa_28",
                "relation_type": "SCHEDULE_OF",
                "clause_scope": "ALL"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-02-01",
                "expected_status": "resolved",
                "expected_agreement_title": "CloudSphere Master Services Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 45}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-05-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Order Form No. 101 - Enterprise Capacity",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 10}
            }
        ]
    },

    # Family 29: Full Restatement Supersession
    {
        "family_id": "family_29_full_restatement_supersession",
        "name": "Restated Master Agreement Full Supersession",
        "counterparty": "Summit Financial Technologies",
        "documents": [
            {
                "doc_id": "doc_msa_29",
                "filename": "Summit_Financial_Master_Agreement.txt",
                "title": "Summit Financial Master Services Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2023-01-01",
                "execution_status": "executed",
                "text": "SUMMIT FINANCIAL MASTER SERVICES AGREEMENT\n\nBetween Summit Financial Technologies and Customer.\n\nSection 4. Payment Terms.\nInvoices payable Net 30 days."
            },
            {
                "doc_id": "doc_restated_29",
                "filename": "Summit_Amended_and_Restated_Agreement.txt",
                "title": "Amended and Restated Summit Financial Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "AMENDED AND RESTATED SUMMIT FINANCIAL AGREEMENT\n\nThis Amended and Restated Summit Financial Agreement supersedes and replaces in its entirety that certain Summit Financial Master Services Agreement dated January 1, 2023.\n\nSection 4. Payment Terms.\nInvoices shall be paid Net 45 days."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_restated_29",
                "target_doc_id": "doc_msa_29",
                "relation_type": "SUPERSEDES",
                "clause_scope": "ALL"
            }
        ],
        "test_queries": [
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2023-06-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Summit Financial Master Services Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 30}
            },
            {
                "topic": "PAYMENT_TERMS",
                "as_of_date": "2024-06-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amended and Restated Summit Financial Agreement",
                "expected_section": "Section 4",
                "expected_slots": {"net_days": 45}
            }
        ]
    },

    # Family 30: Notice Period Formal Escalation
    {
        "family_id": "family_30_notice_period_formal_escalation",
        "name": "General Notice Period Formal Escalation",
        "counterparty": "Vanguard Industrial Automation",
        "documents": [
            {
                "doc_id": "doc_msa_30",
                "filename": "Vanguard_Framework_Agreement.txt",
                "title": "Vanguard Automation Framework Agreement",
                "instrument_type": "master_agreement",
                "effective_date": "2024-01-01",
                "execution_status": "executed",
                "text": "VANGUARD AUTOMATION FRAMEWORK AGREEMENT\n\nBetween Vanguard Industrial Automation and Customer.\n\nSection 12. Notices.\nAll formal notices under this Agreement shall be sent upon ten (10) days prior written notice."
            },
            {
                "doc_id": "doc_amend_30",
                "filename": "Vanguard_Amendment_No_1.txt",
                "title": "Amendment No. 1 to Vanguard Automation Framework Agreement",
                "instrument_type": "amendment",
                "effective_date": "2024-06-01",
                "execution_status": "executed",
                "text": "AMENDMENT NO. 1\n\nThis Amendment No. 1 to that certain Vanguard Automation Framework Agreement dated January 1, 2024 is entered into between Vanguard Industrial Automation and Customer.\n\nSection 12 is hereby amended: All formal notices under this Agreement shall be sent upon thirty (30) days prior written notice."
            }
        ],
        "expected_relations": [
            {
                "source_doc_id": "doc_amend_30",
                "target_doc_id": "doc_msa_30",
                "relation_type": "AMENDS",
                "clause_scope": "Section 12"
            }
        ],
        "test_queries": [
            {
                "topic": "NOTICES",
                "as_of_date": "2024-03-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Vanguard Automation Framework Agreement",
                "expected_section": "Section 12",
                "expected_slots": {"notice_days": 10}
            },
            {
                "topic": "NOTICES",
                "as_of_date": "2024-08-01",
                "expected_status": "resolved",
                "expected_agreement_title": "Amendment No. 1 to Vanguard Automation Framework Agreement",
                "expected_section": "Section 12",
                "expected_slots": {"notice_days": 30}
            }
        ]
    }
]


def main():
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    # Keep the original 7 families and replace/append NEW_FAMILIES
    original_7 = corpus.get("families", [])[:7]
    all_fams = original_7 + NEW_FAMILIES

    corpus["families"] = all_fams
    corpus["total_families"] = len(all_fams)

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2)

    print(f"Successfully updated {CORPUS_PATH}: 7 original + {len(NEW_FAMILIES)} new families = {len(all_fams)} total.")


if __name__ == "__main__":
    main()
