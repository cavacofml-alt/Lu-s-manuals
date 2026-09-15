"""Prints the egress matrix by exercising the real guard.

Run: python evaluation/harness/egress_matrix.py
The architecture review asked not to be told "the tests pass" but to be shown the
matrix. This generates it from the code rather than from a document, so it cannot
drift away from what the system actually does.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.adapters.providers import (  # noqa: E402
    ClaudeLLM, ClaudeVision, CloudOcr, CloudReranker, LocalEmbeddings, LocalLLM,
    LocalReranker, LocalVision, TesseractOcr, VoyageEmbeddings,
)
from app.domain.egress import (  # noqa: E402
    Classification, Classified, EgressPolicy, EgressViolation, PolicyMode,
)
from app.services.egress_guard import EgressGuard  # noqa: E402

PROVIDERS = [
    VoyageEmbeddings(), LocalEmbeddings(), ClaudeLLM(), LocalLLM(),
    CloudReranker(), LocalReranker(), ClaudeVision(), LocalVision(),
    CloudOcr(), TesseractOcr(),
]


def check(policy: EgressPolicy, provider, classification: Classification) -> str:
    guard = EgressGuard(policy, {provider.capability: [provider]})
    try:
        guard.release(Classified("document content", classification), provider)
        return "ALLOWED"
    except EgressViolation:
        return "BLOCKED"


def main() -> int:
    failures = 0
    for mode in PolicyMode:
        policy = EgressPolicy(mode=mode)
        print(f"\n=== EGRESS_POLICY_MODE={mode} " + "=" * 46)
        print(f"{'capability':<14}{'provider':<22}{'where':<8}"
              + "".join(f"{c.name[:13]:<15}" for c in Classification))
        for p in PROVIDERS:
            row = [check(policy, p, c) for c in Classification]
            print(f"{p.capability!s:<14}{p.name:<22}{p.locality!s:<8}"
                  + "".join(f"{r:<15}" for r in row))
            for c, r in zip(Classification, row, strict=True):
                sensitive = c in (Classification.CONFIDENTIAL, Classification.HIGHLY_CONFIDENTIAL)
                if sensitive and p.locality.value == "cloud" and r != "BLOCKED":
                    print(f"  !! VIOLATION: {c} reached {p.name}")
                    failures += 1

    print("\n=== startup validation " + "=" * 50)
    cases = [
        ("shipped defaults (local emb + Claude) claiming internal",
         PolicyMode.MIXED, [LocalEmbeddings(), ClaudeLLM()], Classification.INTERNAL),
        ("shipped defaults claiming confidential",
         PolicyMode.MIXED, [LocalEmbeddings(), ClaudeLLM()], Classification.CONFIDENTIAL),
        ("all local, claiming highly_confidential",
         PolicyMode.MIXED, [LocalEmbeddings(), LocalLLM()], Classification.HIGHLY_CONFIDENTIAL),
        ("strict_local with one cloud provider present",
         PolicyMode.STRICT_LOCAL, [LocalEmbeddings(), LocalLLM(), ClaudeVision()],
         Classification.PUBLIC),
        ("strict_local, fully local",
         PolicyMode.STRICT_LOCAL, [LocalEmbeddings(), LocalLLM()],
         Classification.HIGHLY_CONFIDENTIAL),
    ]
    for label, mode, provs, handles in cases:
        by_cap: dict = {}
        for p in provs:
            by_cap.setdefault(p.capability, []).append(p)
        guard = EgressGuard(EgressPolicy(mode=mode), by_cap)
        try:
            guard.validate_startup(handles)
            print(f"  BOOTS            {label}")
        except RuntimeError:
            print(f"  STARTUP FAILURE  {label}")

    print(f"\n{'PROPERTY HOLDS' if failures == 0 else f'{failures} VIOLATIONS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
