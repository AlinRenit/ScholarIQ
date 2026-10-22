"""Architectural guard: ScholarIQ must not depend on external or local AI models.

The first group runs the scanner over the real repository. The second group
plants known-bad files in a temporary tree to prove each rule actually fires,
so a silently broken scanner cannot pass the first group.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholariq.compliance import scanner
from tests.conftest import REPO_ROOT

# --- The real repository ---------------------------------------------------- #


def test_no_prohibited_python_dependencies_declared() -> None:
    assert scanner.scan_python_manifests(REPO_ROOT) == []


def test_no_prohibited_python_distributions_installed() -> None:
    # Catches transitive dependencies that pull in a model runtime.
    assert scanner.scan_installed_distributions() == []


def test_no_ai_sdk_imports_and_offline_intelligence_modules() -> None:
    assert scanner.scan_python_imports(REPO_ROOT) == []


def test_no_prohibited_npm_packages() -> None:
    assert (REPO_ROOT / "frontend" / "package.json").exists()
    assert scanner.scan_npm(REPO_ROOT) == []


def test_no_inference_endpoints_or_ai_credentials_in_source() -> None:
    assert scanner.scan_text(REPO_ROOT) == []


def test_env_example_has_no_secrets() -> None:
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if any(w in key for w in ("SECRET", "PASSWORD", "TOKEN", "KEY")):
            assert value.strip() in {"", "change-me", "scholariq"}, key


# --- The scanner itself ----------------------------------------------------- #


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


@pytest.mark.parametrize(
    ("files", "rule"),
    [
        (
            {"backend/pyproject.toml": '[project]\nname="x"\ndependencies=["openai>=1"]\n'},
            "python-dependency",
        ),
        ({"backend/requirements.txt": "sentence_transformers==3\n"}, "python-dependency"),
        ({"backend/scholariq/x.py": "import anthropic\n"}, "ai-import"),
        ({"backend/scholariq/x.py": "from langchain.llms import X\n"}, "ai-import"),
        (
            {"backend/scholariq/x.py": "import importlib\nimportlib.import_module('ollama')\n"},
            "ai-import",
        ),
        ({"backend/scholariq/retrieval/bm25.py": "import httpx\n"}, "network-in-intelligence"),
        (
            {"backend/scholariq/answering/h.py": "from urllib.request import urlopen\n"},
            "network-in-intelligence",
        ),
        (
            {"frontend/package.json": json.dumps({"dependencies": {"@ai-sdk/openai": "1"}})},
            "npm-dependency",
        ),
        (
            {
                "frontend/package-lock.json": json.dumps(
                    {"packages": {"node_modules/x/node_modules/openai": {}}}
                )
            },
            "npm-dependency",
        ),
        (
            {"frontend/lib/api.ts": "fetch('https://api.openai.com/v1/chat')\n"},
            "inference-endpoint",
        ),
        ({"backend/scholariq/c.py": "URL = 'http://localhost:11434/api'\n"}, "inference-endpoint"),
        ({"docker-compose.yml": "    ANTHROPIC_API_KEY: x\n"}, "ai-env-var"),
        ({".env.example": "HF_TOKEN=\n"}, "ai-env-var"),
    ],
)
def test_scanner_detects(tmp_path: Path, files: dict[str, str], rule: str) -> None:
    root = _tree(tmp_path, files)
    found = scanner.scan_repository(root, include_environment=False)
    assert rule in {v.rule for v in found}, found


def test_scanner_flags_installed_model_runtime() -> None:
    found = scanner.scan_installed_distributions(["FastAPI", "Torch", "llama_cpp_python"])
    assert {v.detail for v in found} == {"torch", "llama-cpp-python"}


def test_scanner_allows_clean_tree(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "backend/scholariq/retrieval/bm25.py": "import math\nfrom collections import Counter\n",
            "backend/scholariq/api/x.py": "import httpx\n",  # API layer may use network libs
            "frontend/package.json": json.dumps({"dependencies": {"next": "16", "aiohttp": "1"}}),
        },
    )
    assert scanner.scan_repository(root, include_environment=False) == []
