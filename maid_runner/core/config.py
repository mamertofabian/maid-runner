"""Project-level configuration for MAID Runner v2."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import math
from pathlib import Path
from pathlib import PureWindowsPath
import re
from typing import Union

import yaml

from maid_runner.core.types import ValidationMode


@dataclass(frozen=True)
class CriticalPathRule:
    pattern: str
    minimum_priority: str


@dataclass(frozen=True)
class CoverageRecommendationConfig:
    critical_paths: tuple[CriticalPathRule, ...] = ()
    entrypoints: tuple[str, ...] = ()
    cache_enabled: bool = True
    deep_command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FixtureLifecycleApproval:
    context_id: str
    conftest_path: str
    sha256: str


@dataclass(frozen=True)
class DistributionFixtureLifecycleApproval:
    context_id: str
    distribution: str
    module_path: str
    sha256: str


@dataclass(frozen=True)
class ArtifactCoverageConfig:
    timeout_seconds: float = 900.0
    fallback_jobs: int = 1
    evidence_mode: str = "exact"
    fixture_lifecycle_approvals: tuple[FixtureLifecycleApproval, ...] = ()
    distribution_fixture_lifecycle_approvals: tuple[
        DistributionFixtureLifecycleApproval, ...
    ] = ()

    def __post_init__(self) -> None:
        raw_timeout = self.timeout_seconds
        if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
            raise ValueError(
                "artifact_coverage.timeout_seconds must be a positive number"
            )
        try:
            normalized_timeout = float(raw_timeout)
        except OverflowError as exc:
            raise ValueError(
                "artifact_coverage.timeout_seconds must be a positive number"
            ) from exc
        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise ValueError(
                "artifact_coverage.timeout_seconds must be a positive number"
            )
        object.__setattr__(self, "timeout_seconds", normalized_timeout)
        if (
            isinstance(self.fallback_jobs, bool)
            or not isinstance(self.fallback_jobs, int)
            or self.fallback_jobs < 1
        ):
            raise ValueError(
                "artifact_coverage.fallback_jobs must be a positive integer"
            )
        mode = self.evidence_mode
        if mode not in {"derived", "exact"}:
            raise ValueError("artifact_coverage.evidence_mode must be derived or exact")
        object.__setattr__(self, "evidence_mode", mode)
        object.__setattr__(
            self,
            "fixture_lifecycle_approvals",
            tuple(self.fixture_lifecycle_approvals),
        )
        object.__setattr__(
            self,
            "distribution_fixture_lifecycle_approvals",
            tuple(self.distribution_fixture_lifecycle_approvals),
        )


@dataclass(frozen=True)
class TestRunnerWrapperConfig:
    command: str
    runner: str


@dataclass(frozen=True)
class TestExecutionConfig:
    """Validated pytest workers and shared process budget."""

    pytest_workers: int | str = 1
    pytest_dist_mode: str = "loadscope"
    accepted_pytest_worker_counts: tuple[int, ...] = ()
    parallel_threshold_seconds: float = 30.0
    parallel_without_history: bool = False
    command_jobs: int = 1
    max_processes: int = 1

    def __post_init__(self) -> None:
        workers = self.pytest_workers
        if isinstance(workers, bool) or not isinstance(workers, (int, str)):
            raise ValueError("test_execution.pytest_workers must be positive or auto")
        if isinstance(workers, int) and workers < 1:
            raise ValueError("test_execution.pytest_workers must be positive or auto")
        if isinstance(workers, str) and workers != "auto":
            raise ValueError("test_execution.pytest_workers must be positive or auto")
        if self.pytest_dist_mode != "loadscope":
            raise ValueError("test_execution.pytest_dist_mode must be loadscope")

        counts = self.accepted_pytest_worker_counts
        if not isinstance(counts, tuple) or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 1
            for value in counts
        ):
            raise ValueError(
                "test_execution.accepted_pytest_worker_counts must contain integers greater than one"
            )
        if len(set(counts)) != len(counts):
            raise ValueError(
                "test_execution.accepted_pytest_worker_counts must be unique"
            )
        object.__setattr__(self, "accepted_pytest_worker_counts", tuple(sorted(counts)))

        threshold = self.parallel_threshold_seconds
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError(
                "test_execution.parallel_threshold_seconds must be finite and non-negative"
            )
        normalized_threshold = float(threshold)
        if not math.isfinite(normalized_threshold) or normalized_threshold < 0:
            raise ValueError(
                "test_execution.parallel_threshold_seconds must be finite and non-negative"
            )
        object.__setattr__(self, "parallel_threshold_seconds", normalized_threshold)

        if not isinstance(self.parallel_without_history, bool):
            raise ValueError("test_execution.parallel_without_history must be boolean")
        for name, value in (
            ("command_jobs", self.command_jobs),
            ("max_processes", self.max_processes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"test_execution.{name} must be a positive integer")

        requested = max(counts) if workers == "auto" and counts else workers
        if workers == "auto" and not counts:
            raise ValueError(
                "test_execution.pytest_workers auto requires an accepted worker count"
            )
        if isinstance(requested, int) and requested > 1 and requested not in counts:
            raise ValueError(
                "test_execution.pytest_workers must be in accepted_pytest_worker_counts"
            )
        if (
            isinstance(requested, int)
            and self.command_jobs * requested > self.max_processes
        ):
            raise ValueError(
                "test_execution command_jobs * pytest_workers exceeds max_processes"
            )


@dataclass(frozen=True)
class KnockoutExecutionConfig:
    """Validated bounded knockout worker configuration."""

    jobs: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.jobs, bool)
            or not isinstance(self.jobs, int)
            or self.jobs < 1
        ):
            raise ValueError("knockout_execution.jobs must be a positive integer")


@dataclass(frozen=True)
class MaidConfig:
    manifest_dir: str = "manifests/"
    schema_version: str = "2"
    default_validation_mode: ValidationMode = ValidationMode.IMPLEMENTATION
    languages: tuple[str, ...] = ("python", "typescript")
    coherence_enabled: bool = False
    coherence_checks: tuple[str, ...] = ()
    test_runner_wrappers: tuple[TestRunnerWrapperConfig, ...] = ()
    coverage_recommendation: CoverageRecommendationConfig = (
        CoverageRecommendationConfig()
    )
    artifact_coverage: ArtifactCoverageConfig = ArtifactCoverageConfig()
    test_execution: TestExecutionConfig = TestExecutionConfig()
    knockout_execution: KnockoutExecutionConfig = KnockoutExecutionConfig()


def load_config(project_root: Union[str, Path]) -> MaidConfig:
    root = Path(project_root)
    config_path = root / ".maidrc.yaml"
    if not config_path.exists():
        return MaidConfig()

    text = config_path.read_text()
    if not text or not text.strip():
        return MaidConfig()

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return MaidConfig()

    coherence = data.get("coherence", {}) or {}
    test_runner_wrappers = _parse_test_runner_wrappers(
        data.get("test_runner_wrappers", []),
        root,
    )
    recommendation = data.get("coverage_recommendation", {}) or {}
    if not isinstance(recommendation, dict):
        raise ValueError("coverage_recommendation must be a mapping")
    raw_rules = recommendation.get("critical_paths", []) or []
    if not isinstance(raw_rules, list):
        raise ValueError("coverage_recommendation.critical_paths must be a list")
    rules: list[CriticalPathRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise ValueError("critical_paths entries must be mappings")
        pattern = raw_rule.get("pattern")
        minimum = raw_rule.get("minimum_priority")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("critical path pattern must be a non-empty string")
        if minimum not in {"low", "medium", "high", "critical"}:
            raise ValueError(
                "critical path minimum_priority must be low, medium, high, or critical"
            )
        rules.append(CriticalPathRule(pattern, minimum))
    raw_entrypoints = recommendation.get("entrypoints", []) or []
    if not isinstance(raw_entrypoints, list) or not all(
        isinstance(item, str) for item in raw_entrypoints
    ):
        raise ValueError("coverage_recommendation.entrypoints must be a string list")
    deep = recommendation.get("deep", {}) or {}
    if not isinstance(deep, dict):
        raise ValueError("coverage_recommendation.deep must be a mapping")
    raw_command = deep.get("command")
    if raw_command is not None and (
        not isinstance(raw_command, list)
        or not raw_command
        or not all(isinstance(item, str) and item for item in raw_command)
    ):
        raise ValueError(
            "coverage_recommendation.deep.command must be a non-empty string list"
        )
    artifact_coverage = data.get("artifact_coverage", {}) or {}
    if not isinstance(artifact_coverage, dict):
        raise ValueError("artifact_coverage must be a mapping")
    raw_artifact_coverage_timeout = artifact_coverage.get("timeout_seconds", 900.0)
    if isinstance(raw_artifact_coverage_timeout, bool) or not isinstance(
        raw_artifact_coverage_timeout, (int, float)
    ):
        raise ValueError("artifact_coverage.timeout_seconds must be a positive number")
    approvals = _parse_fixture_lifecycle_approvals(
        artifact_coverage.get("fixture_lifecycle_approvals", ()), root
    )
    distribution_approvals = _parse_distribution_fixture_lifecycle_approvals(
        artifact_coverage.get("distribution_fixture_lifecycle_approvals", ())
    )
    artifact_coverage_config = ArtifactCoverageConfig(
        timeout_seconds=raw_artifact_coverage_timeout,
        fallback_jobs=artifact_coverage.get("fallback_jobs", 1),
        evidence_mode=artifact_coverage.get("evidence_mode", "exact"),
        fixture_lifecycle_approvals=approvals,
        distribution_fixture_lifecycle_approvals=distribution_approvals,
    )
    test_execution_config = _parse_test_execution(data.get("test_execution", {}))
    knockout_execution_config = _parse_knockout_execution(
        data.get("knockout_execution", {})
    )
    if knockout_execution_config.jobs > test_execution_config.max_processes:
        raise ValueError(
            "knockout_execution.jobs must not exceed test_execution.max_processes"
        )
    if artifact_coverage_config.fallback_jobs > test_execution_config.max_processes:
        raise ValueError(
            "artifact_coverage.fallback_jobs must not exceed "
            "test_execution.max_processes"
        )

    return MaidConfig(
        manifest_dir=data.get("manifest_dir", "manifests/"),
        schema_version=str(data.get("schema_version", "2")),
        default_validation_mode=ValidationMode(
            data.get("default_validation_mode", "implementation")
        ),
        languages=tuple(data.get("languages", ("python", "typescript"))),
        coherence_enabled=bool(coherence.get("enabled", False)),
        coherence_checks=tuple(coherence.get("checks", ())),
        test_runner_wrappers=test_runner_wrappers,
        coverage_recommendation=CoverageRecommendationConfig(
            critical_paths=tuple(rules),
            entrypoints=tuple(raw_entrypoints),
            cache_enabled=bool(recommendation.get("cache", True)),
            deep_command=tuple(raw_command) if raw_command is not None else None,
        ),
        artifact_coverage=artifact_coverage_config,
        test_execution=test_execution_config,
        knockout_execution=knockout_execution_config,
    )


def _parse_knockout_execution(raw: object) -> KnockoutExecutionConfig:
    if raw is None:
        return KnockoutExecutionConfig()
    if not isinstance(raw, dict):
        raise ValueError("knockout_execution must be a mapping")
    unknown = set(raw) - {"jobs"}
    if unknown:
        raise ValueError(
            f"knockout_execution contains unknown keys: {', '.join(sorted(unknown))}"
        )
    return KnockoutExecutionConfig(jobs=raw.get("jobs", 1))


def _parse_fixture_lifecycle_approvals(
    raw: object, project_root: Path
) -> tuple[FixtureLifecycleApproval, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("artifact_coverage.fixture_lifecycle_approvals must be a list")
    root = Path(project_root).resolve()
    approvals = []
    seen = set()
    pattern = re.compile(
        r"^fixture:(?P<baseid>[^:]*):(?P<name>[^:]+):"
        r"(?P<scope>function|class|module|package|session)$"
    )
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "context_id",
            "conftest_path",
            "sha256",
        }:
            raise ValueError("fixture lifecycle approval must be an exact mapping")
        context_id = item["context_id"]
        relative_value = item["conftest_path"]
        digest = item["sha256"]
        if (
            not isinstance(context_id, str)
            or (match := pattern.fullmatch(context_id)) is None
        ):
            raise ValueError("fixture lifecycle approval context_id is invalid")
        if context_id in seen:
            raise ValueError("fixture lifecycle approval context_id must be unique")
        if not isinstance(relative_value, str) or not relative_value:
            raise ValueError("fixture lifecycle approval conftest_path is invalid")
        relative = Path(relative_value)
        if (
            relative.is_absolute()
            or PureWindowsPath(relative_value).is_absolute()
            or ".." in relative.parts
            or relative.suffix != ".py"
        ):
            raise ValueError(
                "fixture lifecycle approval must name a contained Python source"
            )
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ValueError(
                "fixture lifecycle approval conftest_path escapes project"
            ) from exc
        if resolved != candidate.absolute() or not candidate.is_file():
            raise ValueError(
                "fixture lifecycle approval conftest_path must be a regular file"
            )
        expected_baseid = (
            relative.parent.as_posix()
            if relative.name == "conftest.py"
            else relative.as_posix()
        )
        if expected_baseid == ".":
            expected_baseid = ""
        if match.group("baseid") != expected_baseid:
            raise ValueError(
                "fixture lifecycle approval context baseid does not match path"
            )
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("fixture lifecycle approval sha256 must be lowercase hex")
        seen.add(context_id)
        approvals.append(
            FixtureLifecycleApproval(context_id, relative.as_posix(), digest)
        )
    return tuple(approvals)


def _parse_distribution_fixture_lifecycle_approvals(
    raw: object,
) -> tuple[DistributionFixtureLifecycleApproval, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError(
            "artifact_coverage.distribution_fixture_lifecycle_approvals must be a list"
        )
    approvals = []
    seen = set()
    pattern = re.compile(
        r"^fixture::(?P<name>[^:]+):"
        r"(?P<scope>function|class|module|package|session)$"
    )
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "context_id",
            "distribution",
            "module_path",
            "sha256",
        }:
            raise ValueError(
                "distribution fixture lifecycle approval must be an exact mapping"
            )
        context_id = item["context_id"]
        distribution_name = item["distribution"]
        module_value = item["module_path"]
        digest = item["sha256"]
        if not isinstance(context_id, str) or pattern.fullmatch(context_id) is None:
            raise ValueError(
                "distribution fixture lifecycle approval context_id is invalid"
            )
        if context_id in seen:
            raise ValueError(
                "distribution fixture lifecycle approval context_id must be unique"
            )
        if not isinstance(distribution_name, str) or not distribution_name:
            raise ValueError(
                "distribution fixture lifecycle approval distribution is invalid"
            )
        if not isinstance(module_value, str) or not module_value:
            raise ValueError(
                "distribution fixture lifecycle approval module_path is invalid"
            )
        relative = Path(module_value)
        if (
            relative.is_absolute()
            or PureWindowsPath(module_value).is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError(
                "distribution fixture lifecycle approval module_path must be relative"
            )
        try:
            distribution = importlib.metadata.distribution(distribution_name)
            root = Path(distribution.locate_file("")).resolve(strict=True)
            candidate = Path(distribution.locate_file(relative))
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (importlib.metadata.PackageNotFoundError, OSError, ValueError) as exc:
            raise ValueError(
                "distribution fixture lifecycle approval module_path is unavailable"
            ) from exc
        if resolved != candidate.absolute() or not candidate.is_file():
            raise ValueError(
                "distribution fixture lifecycle approval module_path must be a regular contained file"
            )
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(
                "distribution fixture lifecycle approval sha256 must be lowercase hex"
            )
        seen.add(context_id)
        approvals.append(
            DistributionFixtureLifecycleApproval(
                context_id,
                distribution_name,
                relative.as_posix(),
                digest,
            )
        )
    return tuple(approvals)


def _parse_test_execution(raw: object) -> TestExecutionConfig:
    if raw is None:
        return TestExecutionConfig()
    if not isinstance(raw, dict):
        raise ValueError("test_execution must be a mapping")
    allowed = {
        "pytest_workers",
        "pytest_dist_mode",
        "accepted_pytest_worker_counts",
        "parallel_threshold_seconds",
        "parallel_without_history",
        "command_jobs",
        "max_processes",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(
            f"test_execution contains unknown keys: {', '.join(sorted(unknown))}"
        )
    raw_counts = raw.get("accepted_pytest_worker_counts", ())
    if not isinstance(raw_counts, (list, tuple)):
        raise ValueError("test_execution.accepted_pytest_worker_counts must be a list")
    return TestExecutionConfig(
        pytest_workers=raw.get("pytest_workers", 1),
        pytest_dist_mode=raw.get("pytest_dist_mode", "loadscope"),
        accepted_pytest_worker_counts=tuple(raw_counts),
        parallel_threshold_seconds=raw.get("parallel_threshold_seconds", 30.0),
        parallel_without_history=raw.get("parallel_without_history", False),
        command_jobs=raw.get("command_jobs", 1),
        max_processes=raw.get("max_processes", 1),
    )


def _parse_test_runner_wrappers(
    raw_wrappers: object,
    project_root: Path,
) -> tuple[TestRunnerWrapperConfig, ...]:
    if raw_wrappers is None:
        return ()
    if not isinstance(raw_wrappers, list):
        raise ValueError("test_runner_wrappers must be a list")

    wrappers: list[TestRunnerWrapperConfig] = []
    seen_commands: set[str] = set()
    for raw_wrapper in raw_wrappers:
        if not isinstance(raw_wrapper, dict):
            raise ValueError("test_runner_wrappers entries must be mappings")
        if set(raw_wrapper) != {"command", "runner"}:
            raise ValueError(
                "test_runner_wrappers entries require only command and runner"
            )

        command = raw_wrapper.get("command")
        runner = raw_wrapper.get("runner")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("test runner wrapper command must be a non-empty string")
        if runner != "django":
            raise ValueError("test runner wrapper runner must be django")

        normalized = _normalize_test_runner_wrapper_command(command, project_root)
        if normalized in seen_commands:
            raise ValueError(f"duplicate test runner wrapper command: {normalized}")
        seen_commands.add(normalized)
        wrappers.append(TestRunnerWrapperConfig(normalized, runner))

    return tuple(wrappers)


def _normalize_test_runner_wrapper_command(command: str, project_root: Path) -> str:
    candidate = Path(command)
    windows_candidate = PureWindowsPath(command)
    if candidate.is_absolute() or windows_candidate.is_absolute():
        raise ValueError("test runner wrapper command must be project-relative")
    if (
        windows_candidate.drive
        or ".." in candidate.parts
        or ".." in windows_candidate.parts
    ):
        raise ValueError("test runner wrapper command must stay inside the project")

    normalized = candidate.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in {"", "."} or len(Path(normalized).parts) < 2:
        raise ValueError(
            "test runner wrapper command must include a project-relative path"
        )

    root = project_root.resolve()
    try:
        resolved = (project_root / normalized).resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            "test runner wrapper command must stay inside the project"
        ) from exc
    if not resolved.is_file():
        raise ValueError(
            f"test runner wrapper command does not name an existing file: {normalized}"
        )
    return normalized
