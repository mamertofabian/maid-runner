"""Coherence validation package - exports all coherence validation components."""

# Result types
from maid_runner.coherence.result import (
    CoherenceIssue,
    CoherenceResult,
    IssueSeverity,
    IssueType,
)

# Validator
from maid_runner.coherence.validator import CoherenceValidator

# Check functions
from maid_runner.coherence.checks import (
    check_duplicate_artifacts,
    check_signature_conflicts,
    check_module_boundaries,
    check_naming_conventions,
    check_dependency_availability,
    check_pattern_consistency,
    check_architectural_constraints,
    load_constraint_config,
    ConstraintConfig,
    ConstraintRule,
)

# Explicit re-exports for MAID validation (X = X pattern)
CoherenceIssue = CoherenceIssue
CoherenceResult = CoherenceResult
IssueSeverity = IssueSeverity
IssueType = IssueType
CoherenceValidator = CoherenceValidator
check_duplicate_artifacts = check_duplicate_artifacts
check_signature_conflicts = check_signature_conflicts
check_module_boundaries = check_module_boundaries
check_naming_conventions = check_naming_conventions
check_dependency_availability = check_dependency_availability
check_pattern_consistency = check_pattern_consistency
check_architectural_constraints = check_architectural_constraints
load_constraint_config = load_constraint_config
ConstraintConfig = ConstraintConfig
ConstraintRule = ConstraintRule

__all__ = [
    # Result types
    "CoherenceIssue",
    "CoherenceResult",
    "IssueSeverity",
    "IssueType",
    # Validator
    "CoherenceValidator",
    # Check functions
    "check_duplicate_artifacts",
    "check_signature_conflicts",
    "check_module_boundaries",
    "check_naming_conventions",
    "check_dependency_availability",
    "check_pattern_consistency",
    "check_architectural_constraints",
    "load_constraint_config",
    "ConstraintConfig",
    "ConstraintRule",
]
