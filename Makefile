# MAID Runner Development Makefile
# Convenience commands for development workflow

.PHONY: help test validate watch dev install-dev

help:
	@echo "MAID Runner Development Commands:"
	@echo "  make test          - Run all tests"
	@echo "  make validate      - Validate all manifests"
	@echo "  make watch TASK=005 - Watch and test specific task"
	@echo "  make dev TASK=005  - Run tests once for specific task"
	@echo "  make install-dev   - Install development dependencies"

# Run all tests
test:
	uv run python -m pytest tests/ -v

# Validate all manifests
validate:
	@for manifest in manifests/task-*.manifest.json; do \
		echo "Validating $$manifest..."; \
		uv run python validate_manifest.py $$manifest --quiet || exit 1; \
	done
	@echo "✅ All manifests valid"

# Watch mode for specific task (e.g., make watch TASK=005)
watch:
	@if [ -z "$(TASK)" ]; then \
		echo "❌ Specify TASK number, e.g.: make watch TASK=005"; \
		exit 1; \
	fi
	@manifest=$$(ls manifests/task-$(TASK)*.manifest.json 2>/dev/null | head -1); \
	if [ -z "$$manifest" ]; then \
		echo "❌ No manifest found for task $(TASK)"; \
		exit 1; \
	fi; \
	echo "👁️  Watching task $(TASK): $$manifest"; \
	uv run python dev_bootstrap.py $$manifest --watch

# Run once for specific task (e.g., make dev TASK=005)
dev:
	@if [ -z "$(TASK)" ]; then \
		echo "❌ Specify TASK number, e.g.: make dev TASK=005"; \
		exit 1; \
	fi
	@manifest=$$(ls manifests/task-$(TASK)*.manifest.json 2>/dev/null | head -1); \
	if [ -z "$$manifest" ]; then \
		echo "❌ No manifest found for task $(TASK)"; \
		exit 1; \
	fi; \
	echo "🚀 Running task $(TASK): $$manifest"; \
	uv run python dev_bootstrap.py $$manifest --once

# Install development dependencies
install-dev:
	uv pip install watchdog pytest-watch

# Quick validation commands for common tasks
validate-001:
	uv run python validate_manifest.py manifests/task-001-add-schema-validation.manifest.json

validate-002:
	uv run python validate_manifest.py manifests/task-002-add-ast-alignment-validation.manifest.json

validate-003:
	uv run python validate_manifest.py manifests/task-003-behavioral-validation.manifest.json

validate-004:
	uv run python validate_manifest.py manifests/task-004-behavioral-test-integration.manifest.json

# Run specific test files
test-schema:
	uv run pytest tests/test_validate_schema.py -v

test-behavioral:
	uv run pytest tests/test_task_003_behavioral_validation.py -v

test-integration:
	uv run pytest tests/test_task_004_behavioral_test_integration.py -v

# Code quality checks
lint:
	uv run ruff check .

format:
	uv run black .