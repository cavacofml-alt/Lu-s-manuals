"""No network client outside the adapter layer.

The fourth review found the real weakness in the previous inventory test: it walked
`app/adapters/` only, so a component placed anywhere else escaped it. `app/adapters/`
was becoming the new `ports.py` — a boundary that holds only while everyone remembers
where to put things. Each of these passed CI untouched:

    app/services/fake_cloud.py          CloudTranslator.translate(text) -> httpx.post
    app/document_processing/cloud_parser.py   parse_pdf(bytes) -> httpx.post
    app/services/exfil.py               send_to_external_service(payload) -> httpx.post

Naming and inheritance cannot catch those, because the author of such a module is
precisely the person who did not know about `Provider`. What all three *do* have in
common is structural: sending content anywhere requires a network client. So the rule
is about capability rather than convention —

    only the adapter layer may import a network client, and only through a Provider.

This is checked by reading imports, so it holds for a class, a function, a coroutine or
a module-level statement alike. See docs/ARCHITECTURE.md §8.1.5 for what it does not
catch.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

NETWORK_MODULES = {
    "httpx",
    "requests",
    "aiohttp",
    "urllib.request",
    "urllib3",
    "http.client",
    "socket",
    "ftplib",
    "smtplib",
    "boto3",
    "botocore",
    "anthropic",
    "openai",
    "voyageai",
    "cohere",
}

ALLOWED_DIRS = {"adapters"}
"""Only the adapter layer may hold a network client, and only inside a Provider."""

EXEMPT_FILES: dict[str, str] = {}
"""Files allowed a network import outside the adapter layer, each with a reason.

Empty by design. An entry here is a deliberate hole in the boundary and must be argued
for in the diff that adds it.
"""


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _is_network(module: str) -> bool:
    return any(module == n or module.startswith(n + ".") for n in NETWORK_MODULES)


def test_no_network_client_outside_the_adapter_layer() -> None:
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP)
        if str(rel) in EXEMPT_FILES:
            continue
        if rel.parts and rel.parts[0] in ALLOWED_DIRS:
            continue
        network = {m for m in _imported_modules(path) if _is_network(m)}
        if network:
            offenders.append(f"app/{rel} imports {', '.join(sorted(network))}")

    assert not offenders, (
        "Network clients found outside the adapter layer:\n  "
        + "\n  ".join(offenders)
        + "\n\nAnything that can send document content off this machine belongs in "
        "app/adapters/ as a Provider, declaring a Capability and a Locality, reachable "
        "only through EgressGuard.release(). If this module genuinely cannot carry "
        "document content, add it to EXEMPT_FILES with the reason."
    )


def test_network_clients_in_the_adapter_layer_live_beside_a_provider() -> None:
    """A network client inside app/adapters/ must sit in a module defining a Provider.

    Catches the other half: putting the component in the right directory but not making
    it a Provider, which the inventory test only sees for classes.
    """
    offenders: list[str] = []
    for path in sorted((APP / "adapters").rglob("*.py")):
        network = {m for m in _imported_modules(path) if _is_network(m)}
        if not network:
            continue
        source = path.read_text()
        if "Provider)" not in source and "(Provider" not in source:
            offenders.append(
                f"app/adapters/{path.relative_to(APP / 'adapters')} imports "
                f"{', '.join(sorted(network))} but defines no Provider subclass"
            )

    assert not offenders, "\n  ".join(["Network client without a Provider:", *offenders])
