"""Repository contract checks and JSON Schema validation.

This module is deliberately dependency-light: it uses ``jsonschema`` and
``referencing`` only when validating data, so structural checks can run even in
a minimal environment.

Owner: R4 (quality & delivery). See AGENT.md §7 (quality gates).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

SCHEMA_GLOB = "schemas/**/*.schema.json"
SCHEMA_ID_PREFIX = "https://knowflow.local/schemas/"

REQUIRED_DIRS: tuple[str, ...] = (
    "schemas/input",
    "schemas/output",
    "schemas/llm",
    "data/raw",
    "data/interim",
    "src/knowflow",
    "tests/contract",
    "tests/fixtures",
    "examples/synthetic/input",
    "scripts",
    ".github/workflows",
)

REQUIRED_FILES: tuple[str, ...] = (
    "AGENT.md",
    "README.md",
    "shortcuts.md",
    "CHANGELOG.md",
    ".gitignore",
    ".gitattributes",
    ".env.example",
    "pyproject.toml",
    "schemas/README.md",
    "schemas/CONTRACT.md",
    "data/README.md",
    "data/manifests/official-v1.structure.json",
    "scripts/ingest_raw.py",
    "examples/README.md",
    "examples/synthetic/README.md",
    "tests/conftest.py",
    "tests/contract/test_schemas.py",
    "tests/fixtures/README.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/ci.yml",
)

GITIGNORE_MARKERS: tuple[str, ...] = (
    "data/raw/",
    "data/interim/",
    ".env",
    "*.csv",
    "*.xlsx",
    "*.pt",
    "artifacts/",
)

RESTRICTED_DIRS: tuple[str, ...] = ("data/raw", "data/interim")
ALLOWED_RESTRICTED_FILES = {".gitkeep", "README.md"}


def repo_root(start: Path | None = None) -> Path:
    """Find the KnowFlow repository root by walking up from *start*."""

    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for parent in (current, *current.parents):
        if (parent / "pyproject.toml").is_file() and (
            (parent / "AGENT.md").is_file() or (parent / "AGENTS.md").is_file()
        ):
            return parent
    raise FileNotFoundError(
        "Could not locate the KnowFlow repository root "
        "(expected pyproject.toml and AGENT.md)."
    )


def iter_schema_paths(root: Path | None = None) -> list[Path]:
    """Return every JSON Schema under ``schemas/``, sorted for determinism."""

    base = root or repo_root()
    return sorted((base / "schemas").glob("**/*.schema.json"))


def load_json(path: Path) -> Any:
    """Load a UTF-8 JSON file, raising a readable error on failure."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - message is the point
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def _git_ignored(root: Path, rels: list[str]) -> set[str] | None:
    """Return the subset of *rels* that Git ignores, or ``None`` if Git is unusable."""

    if not rels:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"],
            input="\0".join(rels) + "\0",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # 0 = at least one path is ignored, 1 = none is, anything else = Git error.
    if proc.returncode not in (0, 1):
        return None
    return {chunk for chunk in proc.stdout.split("\0") if chunk}


def _check_restricted_dir(root: Path, rel: str) -> Iterable[str]:
    """Restricted data may sit on disk; it must never be committed.

    Official material is *placed* under ``data/raw/<dataset_id>/`` on purpose
    (see ``data/README.md``); the risk is committing it, not storing it. Asking
    Git itself is the only check that reflects that risk, so a CI checkout
    without the local data and a working copy holding 73 MB of it both pass.
    """

    base = root / rel
    if not base.exists():
        return
    files = [
        path
        for path in base.rglob("*")
        if path.is_file() and path.name not in ALLOWED_RESTRICTED_FILES
    ]
    if not files:
        return
    rels = [path.relative_to(root).as_posix() for path in files]
    ignored = _git_ignored(root, rels)
    if ignored is None:
        # No usable Git (rare: an exported tarball). CI always has Git, and
        # replaying .gitignore rules by hand would only drift from Git's own.
        return
    for relpath in rels:
        if relpath not in ignored:
            yield (
                f"{relpath}: restricted data file is not git-ignored and would be "
                "committed (data/raw and data/interim must stay out of the repository)"
            )


def check_repo(root: Path | None = None) -> list[str]:
    """Return a list of contract violations; an empty list means OK."""

    base = root or repo_root()
    errors: list[str] = []

    for rel in REQUIRED_DIRS:
        if not (base / rel).is_dir():
            errors.append(f"missing directory: {rel}")

    for rel in REQUIRED_FILES:
        path = base / rel
        if not path.is_file():
            errors.append(f"missing file: {rel}")
        elif path.stat().st_size == 0:
            errors.append(f"empty required file: {rel}")

    schema_ids: dict[str, Path] = {}
    for path in iter_schema_paths(base):
        try:
            schema = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not isinstance(schema, dict):
            errors.append(f"{path.relative_to(base)}: schema root must be an object")
            continue
        for key in ("$schema", "$id", "title", "type"):
            if key not in schema:
                errors.append(f"{path.relative_to(base)}: missing {key}")
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            if not schema_id.startswith(SCHEMA_ID_PREFIX):
                errors.append(
                    f"{path.relative_to(base)}: $id must start with {SCHEMA_ID_PREFIX}"
                )
            if schema_id in schema_ids:
                errors.append(
                    f"duplicate $id: {schema_id} "
                    f"({schema_ids[schema_id].relative_to(base)} and "
                    f"{path.relative_to(base)})"
                )
            schema_ids[schema_id] = path

    for rel in RESTRICTED_DIRS:
        errors.extend(_check_restricted_dir(base, rel))

    env_file = base / ".env"
    if env_file.exists():
        errors.append(".env must not be committed; use .env.example for variable names")

    gitignore_path = base / ".gitignore"
    if gitignore_path.is_file():
        gitignore = gitignore_path.read_text(encoding="utf-8")
        for marker in GITIGNORE_MARKERS:
            if marker not in gitignore:
                errors.append(f".gitignore: missing marker {marker!r}")

    for rel in ("README.md", "AGENT.md", "shortcuts.md"):
        path = base / rel
        if path.is_file() and path.stat().st_size < 100:
            errors.append(f"{rel}: unexpectedly small for an entry document")

    return errors


def build_registry(root: Path | None = None):
    """Build a ``referencing`` registry for every schema in the repository."""

    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    base = root or repo_root()
    resources: list[tuple[str, Any]] = []
    for path in iter_schema_paths(base):
        schema = load_json(path)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str):
            raise ValueError(f"{path}: schema has no $id")
        resources.append(
            (
                schema_id,
                Resource.from_contents(
                    schema, default_specification=DRAFT202012
                ),
            )
        )
    return Registry().with_resources(resources)


def _format_error(error: Any) -> str:
    path = "/".join(str(part) for part in error.absolute_path)
    location = f"/{path}" if path else "<root>"
    return f"{location}: {error.message}"


def validate_instance(
    schema_path: Path | str,
    data_path: Path | str,
    root: Path | None = None,
) -> list[str]:
    """Validate *data_path* against *schema_path*; return human-readable errors."""

    from jsonschema import Draft202012Validator

    schema_file = Path(schema_path)
    data_file = Path(data_path)
    base = root or repo_root(schema_file)

    schema = load_json(schema_file)
    instance = load_json(data_file)
    validator = Draft202012Validator(schema, registry=build_registry(base))
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda err: (tuple(str(part) for part in err.absolute_path), err.message),
    )
    return [_format_error(error) for error in errors]
