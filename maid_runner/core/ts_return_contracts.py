"""Typed semantic return proofs, separate from syntactic artifact collection."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from maid_runner.core.ts_compiler_resolver import _run_compiler_request


@dataclass(frozen=True)
class ReturnContractExpectation:
    """One unannotated named declaration and its expected type expression."""

    name: str
    line: int
    expected_type: str


@dataclass(frozen=True)
class ReturnContractItem:
    """A semantic result; display text is advisory, never the comparison key."""

    name: str
    line: int
    status: Literal["matched", "mismatched", "unavailable"]
    inferred_type: str | None
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ReturnContractResult:
    """Proof batch with source and effective compiler provenance."""

    source_sha256: str
    compiler_version: str | None
    config_path: str | None
    strict_null_checks: bool | None
    items: tuple[ReturnContractItem, ...]


def check_return_contracts(
    project_root: Path,
    source_path: str,
    config_path: str,
    source: str,
    expectations: tuple[ReturnContractExpectation, ...],
    transport: "Callable[[str], str | None] | None" = None,
) -> ReturnContractResult:
    """Prove a source-file batch through the local compiler or supplied transport.

    Transport failures and untrusted replies are observable unavailable results.
    No result mutates source artifacts or substitutes syntactic inference.
    """
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    root = Path(project_root).resolve()
    payload = {
        "command": "checkReturnContracts",
        "projectRoot": str(root),
        "sourcePath": source_path,
        "configPath": config_path,
        "source": source,
        "sourceSha256": source_hash,
        "expectations": [
            {"name": item.name, "line": item.line, "expectedType": item.expected_type}
            for item in expectations
        ],
    }
    request_hash = hashlib.sha256(
        json.dumps(
            [
                source_hash,
                os.path.abspath(root / source_path),
                os.path.abspath(root / config_path),
                [[item.name, item.line, item.expected_type] for item in expectations],
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload["requestSha256"] = request_hash
    try:
        if transport is None:
            response = _run_compiler_request(payload)
        else:
            raw = transport(json.dumps(payload))
            response = json.loads(raw) if raw is not None else None
        return _decode_proof(
            response, source_hash, request_hash, root / config_path, expectations
        )
    except (OSError, TimeoutError, ValueError, TypeError) as error:
        return _unavailable(
            source_hash, expectations, f"Compiler return proof unavailable: {error}"
        )


def _unavailable(
    source_hash: str,
    expectations: tuple[ReturnContractExpectation, ...],
    message: str,
) -> ReturnContractResult:
    return ReturnContractResult(
        source_sha256=source_hash,
        compiler_version=None,
        config_path=None,
        strict_null_checks=None,
        items=tuple(
            ReturnContractItem(item.name, item.line, "unavailable", None, (message,))
            for item in expectations
        ),
    )


def _decode_proof(
    response: object,
    source_hash: str,
    request_hash: str,
    config_path: Path,
    expectations: tuple[ReturnContractExpectation, ...],
) -> ReturnContractResult:
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise ValueError("compiler transport failed or returned an invalid envelope")
    result = response.get("result")
    if not isinstance(result, dict) or result.get("sourceSha256") != source_hash:
        raise ValueError("missing proof or source hash mismatch")
    if result.get("requestSha256") != request_hash:
        raise ValueError("proof request fingerprint mismatch")
    version = result.get("compilerVersion")
    config = result.get("configPath")
    strict = result.get("strictNullChecks")
    for value in (version, config):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("invalid compiler provenance")
    if config is not None and Path(config).resolve() != config_path.resolve():
        raise ValueError("config provenance mismatch")
    if strict is not None and type(strict) is not bool:
        raise ValueError("invalid strictNullChecks provenance")
    raw_items = result.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != len(expectations):
        raise ValueError("proof batch identity/count mismatch")
    items = []
    for raw, expectation in zip(raw_items, expectations):
        if (
            not isinstance(raw, dict)
            or raw.get("name") != expectation.name
            or type(raw.get("line")) is not int
            or raw["line"] != expectation.line
        ):
            raise ValueError("declaration identity mismatch")
        status = raw.get("status")
        inferred = raw.get("inferredType")
        diagnostics = raw.get("diagnostics")
        if status not in ("matched", "mismatched", "unavailable"):
            raise ValueError("invalid proof status")
        if inferred is not None and (
            not isinstance(inferred, str) or not inferred.strip()
        ):
            raise ValueError("invalid inferred type")
        if not isinstance(diagnostics, list) or any(
            not isinstance(message, str) or not message.strip()
            for message in diagnostics
        ):
            raise ValueError("invalid diagnostics")
        if status == "unavailable":
            if not diagnostics:
                raise ValueError("unavailable proof omitted diagnostics")
        elif not version or not config or strict is None or not inferred or diagnostics:
            raise ValueError("unsafe proof lacks valid compiler provenance")
        items.append(
            ReturnContractItem(
                expectation.name, expectation.line, status, inferred, tuple(diagnostics)
            )
        )
    return ReturnContractResult(source_hash, version, config, strict, tuple(items))
