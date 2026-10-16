#!/usr/bin/env python3
"""Run a bounded local baseline batch for already-supported C facts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen2.5-coder:14b"
MODEL_DIGEST = "9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class ModelIdentity:
    name: str
    digest: str


def request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=900) as response:
            result = json.loads(response.read().decode("utf-8"))
    except OSError as error:
        raise ValueError(f"Ollama request failed: {error}") from error
    if not isinstance(result, dict):
        raise ValueError("Ollama response must be a JSON object")
    return result


def endpoint(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS or parsed.path not in ("", "/"):
        raise ValueError("endpoint must be HTTP on localhost, 127.0.0.1, or ::1")
    return value.rstrip("/")


def model(base_url: str) -> ModelIdentity:
    models = request_json(f"{base_url}/api/tags").get("models")
    if not isinstance(models, list):
        raise ValueError("Ollama model list does not contain models")
    for item in models:
        if isinstance(item, dict) and item.get("name") == MODEL:
            if item.get("digest") != MODEL_DIGEST:
                raise ValueError("installed model digest does not match the approved baseline")
            return ModelIdentity(MODEL, MODEL_DIGEST)
    raise ValueError(f"required local model is not installed: {MODEL}")


def facts(directory: Path, limit: int) -> list[dict[str, Any]]:
    result = []
    for path in sorted(directory.glob("*.json")):
        fact = json.loads(path.read_text(encoding="utf-8"))
        if fact.get("fact_schema") != "sourcebridge.c.ast-facts.v1":
            raise ValueError(f"{path} has an unsupported fact schema")
        source = fact.get("source")
        if not isinstance(source, dict) or not isinstance(source.get("path"), str) or not isinstance(source.get("sha256"), str):
            raise ValueError(f"{path} has incomplete source provenance")
        result.append(fact)
        if len(result) == limit:
            return result
    raise ValueError(f"only {len(result)} C fact files are available")


def identity(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_schema": fact["fact_schema"],
        "source_path": fact["source"]["path"],
        "source_sha256": fact["source"]["sha256"],
        "variant": fact["variant"],
        "functions": fact["functions"],
    }


def payload(entry: dict[str, Any]) -> dict[str, Any]:
    schema = {
        "type": "object",
        "required": [
            "status_claim",
            "fact_schema",
            "source_path",
            "source_sha256",
            "variant",
            "functions",
            "recommendation",
            "open_question",
        ],
        "properties": {
            "status_claim": {"const": "unvalidated-llm-proposal"},
            "fact_schema": {"type": "string"},
            "source_path": {"type": "string"},
            "source_sha256": {"type": "string"},
            "variant": {"type": "object"},
            "functions": {"type": "array"},
            "recommendation": {"enum": ["no_change_needed", "review_fact_boundary"]},
            "open_question": {"type": "string"},
        },
        "additionalProperties": False,
    }
    return {
        "model": MODEL,
        "stream": False,
        "keep_alive": "30m",
        "format": schema,
        "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a C-to-Rust conversion baseline assistant. Return exactly one JSON object. "
                    "The supplied compiler facts are already accepted by the strict native lowering path. "
                    "Copy every fact field exactly. Do not invent C source, test cases, Rust output, or a rule. "
                    "Recommend no_change_needed unless the facts themselves expose a bounded fact-model question."
                ),
            },
            {"role": "user", "content": json.dumps(entry, sort_keys=True)},
        ],
    }


def validate(entry: dict[str, Any], proposal: Any) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise ValueError("proposal is not an object")
    expected = {"status_claim", *entry, "recommendation", "open_question"}
    if set(proposal) != expected:
        raise ValueError("proposal fields differ from the baseline schema")
    for field, value in entry.items():
        if proposal[field] != value:
            raise ValueError(f"proposal changed evidence field `{field}`")
    if proposal["status_claim"] != "unvalidated-llm-proposal":
        raise ValueError("proposal status claim is invalid")
    if proposal["recommendation"] not in {"no_change_needed", "review_fact_boundary"}:
        raise ValueError("proposal recommendation is invalid")
    if not isinstance(proposal["open_question"], str):
        raise ValueError("proposal open question is invalid")
    return proposal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "ollama-fact-baseline")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be between 1 and 20")
    base_url = endpoint(args.endpoint)
    queue = [identity(fact) for fact in facts(args.facts_dir, args.limit)]
    if args.dry_run:
        print(json.dumps({"language": "c", "entries": queue}, indent=2, sort_keys=True))
        return 0
    identity_model = model(base_url)
    session_id = hashlib.sha256(
        json.dumps({"model": asdict(identity_model), "entries": queue}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    outcomes = []
    try:
        for sequence, entry in enumerate(queue, start=1):
            started = time.monotonic()
            raw = request_json(f"{base_url}/api/chat", payload(entry))
            elapsed_seconds = time.monotonic() - started
            content = raw.get("message", {}).get("content") if isinstance(raw.get("message"), dict) else None
            record = {
                "status": "unvalidated-llm-proposal",
                "worker_session_id": session_id,
                "sequence": sequence,
                "model": asdict(identity_model),
                "input": entry,
                "elapsed_seconds": elapsed_seconds,
                "raw_response": raw,
            }
            try:
                record["proposal"] = validate(entry, json.loads(content) if isinstance(content, str) else None)
                target = args.output_dir / "staged"
            except (ValueError, json.JSONDecodeError) as error:
                record["proposal"] = None
                record["rejection_reason"] = str(error)
                target = args.output_dir / "rejected"
            target.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(
                json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            path = target / f"{digest}.json"
            path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            outcomes.append({"sequence": sequence, "status": record["status"] if target.name == "staged" else "rejected"})
    finally:
        request_json(f"{base_url}/api/generate", {"model": MODEL, "keep_alive": 0})
    print(json.dumps({"language": "c", "session_id": session_id, "outcomes": outcomes}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
