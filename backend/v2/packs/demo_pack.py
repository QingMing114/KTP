from __future__ import annotations

from v2.shared.schemas import DomainPackSummary


def build_demo_pack() -> DomainPackSummary:
    return DomainPackSummary(
        name="demo",
        status="ready",
        description="Minimal generic demonstration pack used to prove V2 is not KTP-only.",
        entry_tools=["demo.pack_answer", "demo.fail"],
    )


def build_ktp_placeholder_pack() -> DomainPackSummary:
    return DomainPackSummary(
        name="ktp",
        status="partial",
        description="KTP domain pack exposing chat-facing macro tools plus the bounded internal analysis chain.",
        entry_tools=[
            "ktp.analysis_pipeline",
            "ktp.explain_knowledge",
            "ktp.trigger_training",
        ],
    )
