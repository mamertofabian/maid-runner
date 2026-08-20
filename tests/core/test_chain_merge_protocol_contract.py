"""Behavioral regression coverage for the chain-merge evidence protocol."""

from __future__ import annotations

from inspect import isabstract
from pathlib import Path

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import validate


def test_detection_evidence_protocol_contract_does_not_emit_e310() -> None:
    from maid_runner.core.chain_merge import DetectionEvidenceSource

    class RecordedSource:
        def detecting_nodeids_for(self, artifact_key: str) -> tuple[str, ...] | None:
            return ("tests/test_service.py::test_behavior",) if artifact_key else None

    source: DetectionEvidenceSource = RecordedSource()
    assert isinstance(source, DetectionEvidenceSource)
    assert isabstract(DetectionEvidenceSource)
    assert source.detecting_nodeids_for("function:service") == (
        "tests/test_service.py::test_behavior",
    )
    with pytest.raises(NotImplementedError) as exc_info:
        DetectionEvidenceSource.detecting_nodeids_for(source, "function:service")
    assert exc_info.value.args == ()

    result = validate(
        Path("manifests/chain-merge-fragmentation-report.manifest.yaml"),
        mode=ValidationMode.IMPLEMENTATION,
        project_root=Path.cwd(),
        check_stubs=True,
    )

    protocol_e310 = [
        warning
        for warning in result.warnings
        if warning.code == ErrorCode.STUB_FUNCTION_DETECTED
        and "DetectionEvidenceSource.detecting_nodeids_for" in warning.message
    ]
    assert protocol_e310 == []
