"""Coherence checks package - exports all check functions."""

from maid_runner.coherence.checks.duplicate_check import check_duplicate_artifacts
from maid_runner.coherence.checks.signature_check import check_signature_conflicts
from maid_runner.coherence.checks.module_boundary import check_module_boundaries
from maid_runner.coherence.checks.naming_check import check_naming_conventions
from maid_runner.coherence.checks.dependency_check import check_dependency_availability
from maid_runner.coherence.checks.pattern_check import check_pattern_consistency
from maid_runner.coherence.checks.constraint_check import (
    check_architectural_constraints,
    load_constraint_config,
    ConstraintConfig,
    ConstraintRule,
)

# Explicit re-exports for MAID validation
# These assignments make imported names visible as module-level attributes
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
