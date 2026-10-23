"""Static scan of the repository for AI SDKs, inference endpoints, AI
credentials and network access from intelligence modules.

Run directly for a report:  python -m scholariq.compliance.scanner [repo_root]
Exit status is non-zero when violations are found.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from scholariq.compliance import policy

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "var",
}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".yaml", ".yml",
    ".txt", ".ini", ".cfg", ".md", ".env", ".example", ".sh", ".mako",
}  # fmt: skip
TEXT_NAMES = {"Dockerfile", ".env.example", "Makefile"}

# Files that must name prohibited things in order to prohibit them.
POLICY_FILES = {
    "backend/scholariq/compliance/policy.py",
    "backend/tests/test_architecture_compliance.py",
    "backend/tests/test_ai_environment.py",
    "docs/COMPLIANCE.md",
}

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass(frozen=True)
class Violation:
    rule: str
    location: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.location}: {self.detail}"


def _walk(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(p in SKIP_DIRS for p in rel_parts):
            continue
        if path.is_file():
            yield path


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _requirement_name(spec: str) -> str | None:
    m = _REQ_NAME.match(spec)
    return policy.normalise_dist_name(m.group(1)) if m else None


def scan_python_manifests(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for path in _walk(root):
        rel = _rel(root, path)
        specs: list[str] = []
        if path.name == "pyproject.toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            project = data.get("project", {})
            specs += project.get("dependencies", [])
            for group in project.get("optional-dependencies", {}).values():
                specs += group
        elif re.fullmatch(r"requirements.*\.txt", path.name):
            specs += [
                ln
                for ln in path.read_text(encoding="utf-8").splitlines()
                if ln and ln[0] not in "#-"
            ]
        for spec in specs:
            name = _requirement_name(spec)
            if name in policy.PROHIBITED_PYTHON_PACKAGES:
                out.append(Violation("python-dependency", rel, name))
    return out


def scan_installed_distributions(dists: Iterable[str] | None = None) -> list[Violation]:
    names = (
        dists
        if dists is not None
        else (d.metadata["Name"] for d in metadata.distributions() if d.metadata["Name"])
    )
    return [
        Violation("installed-distribution", "python environment", n)
        for n in sorted({policy.normalise_dist_name(n) for n in names})
        if n in policy.PROHIBITED_PYTHON_PACKAGES
    ]


def _imports(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute | ast.Name)
            and getattr(node.func, "attr", getattr(node.func, "id", "")) == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            yield node.lineno, node.args[0].value


def _module_name(root: Path, path: Path) -> str | None:
    backend = root / "backend"
    try:
        rel = path.relative_to(backend)
    except ValueError:
        return None
    return ".".join(rel.with_suffix("").parts)


def scan_python_imports(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for path in _walk(root):
        if path.suffix != ".py" or _rel(root, path) in POLICY_FILES:
            continue
        rel = _rel(root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        module = _module_name(root, path) or ""
        in_intelligence = any(
            module == p or module.startswith(p + ".") for p in policy.INTELLIGENCE_PACKAGES
        )
        for lineno, name in _imports(tree):
            if policy.is_prohibited_import(name):
                out.append(Violation("ai-import", f"{rel}:{lineno}", name))
            if in_intelligence and any(
                name == n or name.startswith(n + ".") for n in policy.NETWORK_MODULES
            ):
                out.append(Violation("network-in-intelligence", f"{rel}:{lineno}", name))
    return out


def _npm_names_from_lock(data: dict[str, object]) -> Iterator[str]:
    packages = data.get("packages", {})
    if isinstance(packages, dict):
        for key in packages:
            if "node_modules/" in key:
                yield key.rsplit("node_modules/", 1)[1]


def scan_npm(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for path in _walk(root):
        rel = _rel(root, path)
        names: list[str] = []
        if path.name == "package.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for field in ("dependencies", "devDependencies", "optionalDependencies",
                          "peerDependencies"):  # fmt: skip
                names += list(data.get(field, {}))
        elif path.name == "package-lock.json":
            names += list(_npm_names_from_lock(json.loads(path.read_text(encoding="utf-8"))))
        for name in sorted(set(names)):
            if policy.is_prohibited_npm(name):
                out.append(Violation("npm-dependency", rel, name))
    return out


def _is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES or path.name.startswith(".env")


_ENV_RE = re.compile(r"\b(" + "|".join(sorted(policy.PROHIBITED_ENV_VARS)) + r")\b")


def scan_text(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for path in _walk(root):
        rel = _rel(root, path)
        if rel in POLICY_FILES or not _is_text(path) or path.name == "package-lock.json":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern in policy.PROHIBITED_HOST_PATTERNS:
                if m := pattern.search(line):
                    out.append(Violation("inference-endpoint", f"{rel}:{lineno}", m.group(0)))
            for m in _ENV_RE.finditer(line):
                out.append(Violation("ai-env-var", f"{rel}:{lineno}", m.group(0)))
    return out


def scan_repository(root: Path, include_environment: bool = True) -> list[Violation]:
    violations = (
        scan_python_manifests(root) + scan_python_imports(root) + scan_npm(root) + scan_text(root)
    )
    if include_environment:
        violations += scan_installed_distributions()
    return violations


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[3]
    violations = scan_repository(root)
    for v in violations:
        print(v)
    print(f"{len(violations)} violation(s) in {root}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
