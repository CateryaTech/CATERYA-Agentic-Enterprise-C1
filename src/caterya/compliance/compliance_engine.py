"""
Compliance Checks — GDPR, EU AI Act, ISO 42001
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ComplianceFinding:
    standard:    str   # "GDPR" | "EU_AI_ACT" | "ISO_42001"
    article:     str
    severity:    str   # "critical" | "high" | "medium" | "low" | "pass"
    description: str
    remediation: str
    automated:   bool = True


@dataclass
class ComplianceReport:
    overall_score: float      # 0–1
    passed:        bool
    findings:      List[ComplianceFinding]
    gdpr_score:    float
    eu_ai_score:   float
    iso42001_score: float
    tenant_id:     Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score":  round(self.overall_score, 4),
            "passed":         self.passed,
            "gdpr_score":     round(self.gdpr_score, 4),
            "eu_ai_score":    round(self.eu_ai_score, 4),
            "iso42001_score": round(self.iso42001_score, 4),
            "tenant_id":      self.tenant_id,
            "findings":       [
                {"standard": f.standard, "article": f.article,
                 "severity": f.severity, "description": f.description}
                for f in self.findings
            ],
            "critical_count": sum(1 for f in self.findings if f.severity == "critical"),
            "high_count":     sum(1 for f in self.findings if f.severity == "high"),
        }


# ── GDPR Checker ──────────────────────────────────────────────────────────────

class GDPRChecker:
    """
    Automated GDPR compliance checks based on system configuration and outputs.
    """

    def check(self, context: Dict[str, Any]) -> Tuple[float, List[ComplianceFinding]]:
        findings = []
        score    = 1.0

        # Art 5(1)(f) — Integrity and confidentiality
        if not context.get("encryption_at_rest"):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 5(1)(f)",
                severity="high",
                description="Data encryption at rest not confirmed.",
                remediation="Enable PostgreSQL TDE or application-level encryption.",
            ))
            score -= 0.15

        # Art 17 — Right to erasure
        if not context.get("erasure_api_available"):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 17",
                severity="high",
                description="Right to erasure (delete) API not implemented.",
                remediation="Implement DELETE /tenant/{id}/user/{id}/data endpoint.",
            ))
            score -= 0.15

        # Art 20 — Data portability
        if not context.get("data_export_available"):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 20",
                severity="medium",
                description="Data portability export not available.",
                remediation="Implement JSON/CSV export for all user data.",
            ))
            score -= 0.1

        # Art 25 — Data protection by design
        if not context.get("pii_auto_redaction"):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 25",
                severity="high",
                description="Automated PII redaction not enabled.",
                remediation="Enable CATERYAGuardrail PII redaction in all agent nodes.",
            ))
            score -= 0.15

        # Art 30 — Records of processing
        if not context.get("provenance_chain_enabled"):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 30",
                severity="medium",
                description="Processing activity records (ProvenanceChain) not enabled.",
                remediation="Enable ProvenanceChain for all tenant workflows.",
            ))
            score -= 0.1

        # Art 33 — Breach notification (72h)
        if not context.get("breach_notification_configured"):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 33",
                severity="medium",
                description="72-hour breach notification process not configured.",
                remediation="Configure Alertmanager to notify DPA within 72h of breach detection.",
            ))
            score -= 0.05

        # Check for PII in outputs
        output_text = context.get("sample_output", "")
        if self._detect_pii_in_output(output_text):
            findings.append(ComplianceFinding(
                standard="GDPR", article="Art. 5(1)(c)",
                severity="critical",
                description="PII detected in agent output without explicit user consent.",
                remediation="CATERYAGuardrail redaction must be applied before output storage.",
            ))
            score -= 0.25

        return max(0.0, score), findings

    @staticmethod
    def _detect_pii_in_output(text: str) -> bool:
        patterns = [
            r"\b\d{3}-\d{2}-\d{4}\b",
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            r"\b(?:\d[ -]?){13,16}\b",
        ]
        return any(re.search(p, text, re.I) for p in patterns)


# ── EU AI Act Checker ─────────────────────────────────────────────────────────

class EUAIActChecker:
    """
    EU AI Act 2024 compliance checks.
    Focuses on: risk classification, transparency, human oversight, accuracy.
    """

    def check(self, context: Dict[str, Any]) -> Tuple[float, List[ComplianceFinding]]:
        findings = []
        score    = 1.0
        risk_class = context.get("ai_risk_class", "limited")  # minimal|limited|high|unacceptable

        # Art 9 — Risk management system
        if not context.get("cos_evaluation_enabled"):
            findings.append(ComplianceFinding(
                standard="EU_AI_ACT", article="Art. 9",
                severity="high",
                description="No automated risk management system (COS evaluation) enabled.",
                remediation="Enable CATERYAEvaluator for all workflow outputs.",
            ))
            score -= 0.2

        # Art 13 — Transparency
        if not context.get("interpretability_explanation"):
            findings.append(ComplianceFinding(
                standard="EU_AI_ACT", article="Art. 13",
                severity="high",
                description="AI system does not provide transparency/interpretability explanations.",
                remediation="Ensure all agents implement explain() and log explanations.",
            ))
            score -= 0.15

        # Art 14 — Human oversight
        if not context.get("human_in_loop_available"):
            findings.append(ComplianceFinding(
                standard="EU_AI_ACT", article="Art. 14",
                severity="medium",
                description="Human oversight mechanism not configured.",
                remediation="Enable HumanConstantStability integration for critical decisions.",
            ))
            score -= 0.1

        # Art 15 — Accuracy, robustness
        stability = context.get("stability_index", 0.0)
        if stability < 0.7:
            findings.append(ComplianceFinding(
                standard="EU_AI_ACT", article="Art. 15",
                severity="high",
                description=f"Stability Index {stability:.4f} below 0.7 — robustness not demonstrated.",
                remediation="Run PerturbationTestRunner and improve agent prompts.",
            ))
            score -= 0.15

        # Art 52 — Transparency for certain AI systems
        if not context.get("ai_disclosure_in_output"):
            findings.append(ComplianceFinding(
                standard="EU_AI_ACT", article="Art. 52",
                severity="low",
                description="AI-generated content not disclosed to end users.",
                remediation="Add 'Generated by CATERYA AI' disclosure to all outputs.",
            ))
            score -= 0.05

        # Recital 12 — Prohibited practices
        cos = context.get("cos_score", 1.0)
        if cos < 0.5:
            findings.append(ComplianceFinding(
                standard="EU_AI_ACT", article="Recital 12 / Art. 5",
                severity="critical",
                description=f"COS {cos:.4f} indicates potential manipulation/deception risk.",
                remediation="Investigate and remediate COS pillar failures before deployment.",
            ))
            score -= 0.3

        return max(0.0, score), findings


# ── ISO 42001 Checker ─────────────────────────────────────────────────────────

class ISO42001Checker:
    """
    ISO/IEC 42001:2023 — AI Management System standard checks.
    """

    def check(self, context: Dict[str, Any]) -> Tuple[float, List[ComplianceFinding]]:
        findings = []
        score    = 1.0

        checks = {
            "ai_policy_documented":       ("6.2", "AI policy not documented.", 0.1),
            "risk_assessment_process":    ("8.2", "AI risk assessment process not defined.", 0.15),
            "incident_response_plan":     ("10.1", "AI incident response plan missing.", 0.1),
            "training_data_documented":   ("8.4", "Training data provenance not documented.", 0.1),
            "bias_testing_performed":     ("8.5", "Bias testing not evidenced.", 0.15),
            "audit_trail_enabled":        ("9.1", "Audit trail (ProvenanceChain) not confirmed.", 0.1),
            "continual_improvement_plan": ("10.2", "Continual improvement plan not documented.", 0.05),
            "stakeholder_impact_assessed": ("4.2", "Stakeholder impact assessment missing.", 0.1),
        }

        for check_key, (article, desc, penalty) in checks.items():
            if not context.get(check_key):
                sev = "high" if penalty >= 0.15 else "medium" if penalty >= 0.1 else "low"
                findings.append(ComplianceFinding(
                    standard="ISO_42001", article=f"ISO 42001 Clause {article}",
                    severity=sev, description=desc,
                    remediation=f"Document and implement process for {article}.",
                ))
                score -= penalty

        return max(0.0, score), findings


# ── Unified Compliance Engine ─────────────────────────────────────────────────

class ComplianceEngine:
    """
    Runs all compliance checks and produces a unified report.

    Usage::

        engine = ComplianceEngine()
        report = engine.check_all(context={
            "encryption_at_rest": True,
            "pii_auto_redaction": True,
            "provenance_chain_enabled": True,
            "cos_evaluation_enabled": True,
            "cos_score": 0.92,
            "stability_index": 0.85,
            "interpretability_explanation": True,
            "human_in_loop_available": True,
            "ai_disclosure_in_output": True,
            "erasure_api_available": True,
            "data_export_available": True,
            "breach_notification_configured": True,
            "ai_policy_documented": True,
            "risk_assessment_process": True,
            "bias_testing_performed": True,
            "audit_trail_enabled": True,
            "ai_risk_class": "limited",
        }, tenant_id="acme")
        print(report.overall_score)  # >= 0.9
    """

    def __init__(self):
        self.gdpr      = GDPRChecker()
        self.eu_ai_act = EUAIActChecker()
        self.iso42001  = ISO42001Checker()

    def check_all(
        self,
        context: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ) -> ComplianceReport:
        gdpr_score,    gdpr_findings    = self.gdpr.check(context)
        eu_score,      eu_findings      = self.eu_ai_act.check(context)
        iso_score,     iso_findings     = self.iso42001.check(context)

        all_findings = gdpr_findings + eu_findings + iso_findings
        overall = (gdpr_score * 0.35 + eu_score * 0.40 + iso_score * 0.25)

        return ComplianceReport(
            overall_score=overall,
            passed=overall >= 0.7,
            findings=all_findings,
            gdpr_score=gdpr_score,
            eu_ai_score=eu_score,
            iso42001_score=iso_score,
            tenant_id=tenant_id,
        )
