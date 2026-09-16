"""Property 7, enforced by inventory rather than by memory.

The third architecture review asked what stops a *future* StorageProvider, cloud
DocumentProcessor or telemetry sink from being created outside the egress policy.

The honest answer for the code as it stood was: nothing. Worse, `app/adapters/ports.py`
declared a parallel set of interfaces taking raw content — `StorageProvider.put(key,
BinaryIO)`, `EmbeddingProvider.embed_documents(list[str])` — with no locality and no
guard. Nothing referenced them, but they looked authoritative, and a developer
implementing storage in STEP 3 would have found them first. That file is deleted.

This test is the replacement. It cannot make a bypass impossible — Python does not allow
that — but it converts "someone forgot" from silence into a CI failure: any class in
`app/adapters/` must either go through the guard or be listed here with a stated reason.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import app.adapters
from app.adapters.providers import Provider
from app.domain.egress import Capability, ContentSink, Locality

EXEMPT: dict[str, str] = {
    "Provider": "the base class itself; it is the mechanism",
}
"""Classes that legitimately do not receive document content.

Adding an entry is a deliberate act with a written justification, reviewable in the
diff. An entry reading "does not touch content" for something that does is the failure
mode this cannot prevent — but it is a lie someone has to write down.
"""


def _adapter_classes() -> list[tuple[str, type]]:
    found: list[tuple[str, type]] = []
    for info in pkgutil.walk_packages(app.adapters.__path__, prefix="app.adapters."):
        module = importlib.import_module(info.name)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__.startswith("app.adapters"):
                found.append((name, obj))
    return found


def test_every_adapter_class_goes_through_the_guard_or_is_explicitly_exempt() -> None:
    offenders = [
        f"{name} ({cls.__module__})"
        for name, cls in _adapter_classes()
        if name not in EXEMPT and not issubclass(cls, Provider)
    ]
    assert not offenders, (
        "These adapter classes are outside the egress policy:\n  "
        + "\n  ".join(offenders)
        + "\n\nA class in app/adapters/ that can receive document content must subclass "
        "Provider, declaring a Capability and a Locality, so it is reachable only "
        "through EgressGuard.release(). If it genuinely never sees content, add it to "
        "EXEMPT with the reason."
    )


def test_every_provider_declares_a_capability_and_a_locality() -> None:
    """A sink cannot exist without stating whether using it discloses content."""
    for name, cls in _adapter_classes():
        if name in EXEMPT or not issubclass(cls, Provider):
            continue
        assert isinstance(getattr(cls, "capability", None), Capability), (
            f"{name} does not declare a Capability"
        )
        assert isinstance(getattr(cls, "locality", None), Locality), (
            f"{name} does not declare a Locality"
        )
        assert isinstance(cls, type) and isinstance(cls(), ContentSink), (
            f"{name} does not satisfy ContentSink"
        )


def test_no_provider_exposes_a_public_method_taking_raw_content() -> None:
    """The gap that let the original bypass work: a public API accepting a bare value.

    `submit` is the only sanctioned entry point. A new public method on a provider is
    how the closed door gets a second handle cut into it.
    """
    allowed = {"submit"}
    offenders: list[str] = []
    for name, cls in _adapter_classes():
        if name in EXEMPT or not issubclass(cls, Provider):
            continue
        for method_name, _ in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith("_") or method_name in allowed:
                continue
            if method_name in vars(Provider):
                continue
            offenders.append(f"{name}.{method_name}")
    assert not offenders, (
        "Providers expose public methods other than submit():\n  "
        + "\n  ".join(offenders)
        + "\n\nContent must enter through submit(Released), which the guard alone can "
        "produce. A second public method is a second way in."
    )


def test_no_orphaned_modules() -> None:
    """A module nothing imports is how `ports.py` happened.

    It was dead code that looked authoritative: a file named "Provider interfaces"
    declaring `StorageProvider.put(key, BinaryIO)` with no locality and no guard, which
    a developer implementing storage would have found and implemented against. Nothing
    referenced it, so nothing failed when it drifted out of line with the real mechanism.

    An orphan is not always wrong — but it should be noticed, not accumulate quietly.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    modules = {
        ".".join(p.relative_to(root).with_suffix("").parts): p
        for p in (root / "app").rglob("*.py")
        if p.name != "__init__.py"
    }

    imported: set[str] = set()
    for source_dir in ("app", "worker", "tests"):
        for path in (root / source_dir).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)

    orphans = [
        str(path.relative_to(root))
        for name, path in sorted(modules.items())
        if name not in imported and not any(i.startswith(name + ".") for i in imported)
    ]
    assert not orphans, (
        "Modules nothing imports:\n  "
        + "\n  ".join(orphans)
        + "\n\nDelete them, or wire them in. Dead code that looks like an interface is "
        "what a future developer will implement against."
    )
