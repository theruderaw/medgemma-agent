"""Enforce the app < registry < addons dependency boundary.

Rules:
1. Nothing outside the composition root (``app/bootstrap.py``) and the
   ``app/addons`` package itself may import ``app.addons`` (or a submodule).
2. Nothing inside ``app/registry`` may import any other ``app.*`` module —
   the neutral layer is import-pure by design.

Exits non-zero listing every violation. Run via ``make check-arch``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
BOOTSTRAP = "app.bootstrap"
ADDONS_PKG = "app.addons"
REGISTRY_PKG = "app.registry"


def module_name(path: Path) -> str:
    relative = path.relative_to(APP_DIR.parent)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve(imported: ast.AST, level: int, source_module: str, is_package: bool) -> str | None:
    """Absolute module name for an Import/ImportFrom entry."""
    if level == 0:
        return getattr(imported, "module", None) or (
            imported.name if isinstance(imported, ast.alias) else None
        )
    base = source_module.split(".") if source_module else []
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    prefix = ".".join(base)
    suffix = getattr(imported, "module", None) or (
        imported.name if isinstance(imported, ast.alias) else None
    )
    return f"{prefix}.{suffix}" if suffix else prefix


def check_file(path: Path) -> list[str]:
    violations: list[str] = []
    source = module_name(path)
    in_addons = source == ADDONS_PKG or source.startswith(ADDONS_PKG + ".")
    in_registry = source == REGISTRY_PKG or source.startswith(REGISTRY_PKG + ".")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    is_package = path.name == "__init__.py"

    for node in ast.walk(tree):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            resolved_root = resolve(node, node.level, source, is_package)
            if node.module:
                targets.append(node.module)
            for alias in node.names:
                full = f"{resolved_root}.{alias.name}" if resolved_root else alias.name
                targets.append(full)
            if not node.module and resolved_root:
                targets.append(resolved_root)
        else:
            continue

        for target in targets:
            if not (target == "app" or target.startswith("app.")):
                continue
            if not in_addons and source != BOOTSTRAP and (
                target == ADDONS_PKG or target.startswith(ADDONS_PKG + ".")
            ):
                violations.append(f"{path}: imports '{target}' outside composition root")
            if in_registry and not target.startswith(REGISTRY_PKG):
                violations.append(
                    f"{path}: registry layer imports application module '{target}'"
                )
    return violations


def main() -> int:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        violations.extend(check_file(path))
    if violations:
        print("ARCHITECTURE VIOLATIONS:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print(f"architecture ok: {APP_DIR} respects app < registry < addons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
