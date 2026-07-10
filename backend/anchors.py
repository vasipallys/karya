"""Deterministic calibration stories. Edit this file to tune team baselines."""

from __future__ import annotations

ANCHORS = [
    {
        "title": "Inline validation on a React payment form",
        "full_text": "Add client-side validation and accessible error summaries to an existing form.",
        "acceptance_criteria": ["Validate four existing fields", "Focus the first error", "Add component tests"],
        "points": 3,
        "rationale": "React-only, established patterns, no service or data changes, modest testing.",
    },
    {
        "title": "Add an entitlement-protected account preference",
        "full_text": "Add a preference in React and persist it through an existing Spring service endpoint.",
        "acceptance_criteria": ["Hide control without entitlement", "Persist and retrieve value", "Audit the change"],
        "points": 5,
        "rationale": "Small cross-stack change using known patterns with entitlement and audit coverage.",
    },
    {
        "title": "Search and filter an existing transaction endpoint",
        "full_text": "Add two indexed filters to an existing API and expose them in the transaction table.",
        "acceptance_criteria": ["Combine filters", "Preserve pagination", "Test query performance"],
        "points": 5,
        "rationale": "Cross-stack but bounded; some database and performance work, little domain uncertainty.",
    },
    {
        "title": "Cross-market eKYC status integration",
        "full_text": "Consume a vendor status API and show normalized eKYC states in two market journeys.",
        "acceptance_criteria": ["Map vendor states", "Apply market residency rules", "Audit transitions", "Handle timeouts"],
        "points": 8,
        "rationale": "Integration-heavy with regulatory rules, failure handling, audit, and multi-market tests.",
    },
    {
        "title": "Transaction-wide AI summary with audit",
        "full_text": "Generate and store a summary across transaction records with traceable model metadata.",
        "acceptance_criteria": ["Write atomically", "Record full audit metadata", "Redact sensitive data", "Support retry"],
        "points": 8,
        "rationale": "Broad Spring and data work with transactional consistency, compliance, and operational uncertainty.",
    },
    {
        "title": "New multi-market payment orchestration journey",
        "full_text": "Create a new UI journey and orchestration service spanning screening, limits, and posting systems.",
        "acceptance_criteria": ["Support three markets", "Compensate partial failures", "Enforce entitlements", "Full audit trail"],
        "points": 13,
        "rationale": "Multiple new layers and external dependencies with high uncertainty; should be split before delivery.",
    },
]
