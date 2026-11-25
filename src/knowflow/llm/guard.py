"""Runtime guard for model output: schema, number lock and ID lock.

A response is accepted only when every number and ID it mentions appears in the
summary whitelist, it cites the issue, and it points at a real material.  The
same whitelist feeds ``verify-recommend``, so accepted text cannot fail the
deterministic gate.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root

NUMBER = re.compile(r"(?<![A-Za-z0-9_-])\d+(?:\.\d+)?(?![A-Za-z0-9_-])")
ID = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:S\d{3}|N\d{2}|G\d|K-\d{2,3}|M-\d{3}|R-\d{4}|IS-\d{3}-\d{2}"
    r"|OBJ-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)"
    r"(?![A-Za-z0-9])"
)
MAX_REASON = 240
MAX_CHECK = 120


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads(
        (root / "schemas" / "llm" / "llm_response.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def parse_json(text: str) -> dict:
    """Parse one JSON object, tolerating a stray code fence."""

    cleaned = (text or "").strip().lstrip("\ufeff")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    return data


def _numbers(text: str) -> set[float]:
    return {float(value) for value in NUMBER.findall(text)}


def response_errors(response: dict, summary: dict) -> list[str]:
    """Return every reason this response must not be written to a plan item."""

    schema_errors = [
        f"llm_response:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in _validator().iter_errors(response)
    ]
    if schema_errors:
        return schema_errors

    errors: list[str] = []
    constraints = summary["constraints"]
    allowed_numbers = {float(value) for value in constraints["allowed_numbers"]}
    allowed_ids = {str(value) for value in constraints["allowed_ids"]}

    if response["kind"] != "recommendation_reason":
        errors.append("kind must be recommendation_reason")
    if response["ref_id"] != summary["ref_id"]:
        errors.append("ref_id must equal the summary ref_id")

    reason = response["reason"]
    check = response.get("check") or ""
    text = reason + ("\n" + check if check else "")
    numbers = _numbers(text)
    unlocked = numbers - allowed_numbers
    if unlocked:
        errors.append(f"reason/check contains unlocked numbers {sorted(unlocked)}")

    mentioned_ids = set(ID.findall(text)) | {str(value) for value in response["cited_ids"]}
    unknown_ids = mentioned_ids - allowed_ids
    if unknown_ids:
        errors.append(f"unknown ids {sorted(unknown_ids)}")
    if summary["ref_id"] not in reason:
        errors.append("reason must cite the issue id")
    if not any(value.startswith("M-") for value in mentioned_ids):
        errors.append("response must cite at least one material id")
    if "http://" in text or "https://" in text or "```" in text:
        errors.append("text must not contain URLs or code fences")
    if len(reason) > MAX_REASON:
        errors.append(f"reason is longer than {MAX_REASON} characters")
    if len(check) > MAX_CHECK:
        errors.append(f"check is longer than {MAX_CHECK} characters")
    return errors
