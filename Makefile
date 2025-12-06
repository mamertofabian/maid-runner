# MAID Runner Development Makefile
# Convenience commands for development workflow

.PHONY: help test validate watch dev install-dev sync-claude build clean dead-code

help:
	@echo "MAID Runner Development Commands:"
	@echo "  make test          - Run all tests"
	@echo "  make validate      - Validate all manifests"
	@echo "  make watch TASK=005 - Watch and test specific task"
	@echo "  make dev TASK=005  - Run tests once for specific task"
	@echo "  make install-dev   - Install development dependencies"
	@echo "  make lint          - Run linting"
	@echo "  make type-check    - Run type checking (alias for lint)"
	@echo "  make lint-fix      - Run linting and fix issues"
	@echo "  make format        - Run formatting"
	@echo "  make dead-code     - Detect unused/dead code with vulture"
	@echo "  make sync-claude   - Sync Claude Code files for package distribution"
	@echo "  make build         - Build package (includes sync-claude)"
	@echo "  make clean         - Clean generated files"

# Run all tests (including structural validation and validation commands from manifests)
test:
	uv run python -m pytest tests/ -v
	@echo ""
	@uv run python scripts/validate_all_manifests.py

# Validate all manifests
validate:
	@for manifest in manifests/task-*.manifest.json; do \
		echo "Validating $$manifest..."; \
		uv run maid validate $$manifest --quiet --use-manifest-chain || exit 1; \
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
	uv run maid test --manifest $$manifest --watch

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
	uv run maid test --manifest $$manifest

# Install development dependencies
install-dev:
	uv pip install watchdog pytest-watch

# Quick validation commands for common tasks
validate-001:
	uv run maid validate manifests/task-001-add-schema-validation.manifest.json

validate-002:
	uv run maid validate manifests/task-002-add-ast-alignment-validation.manifest.json

validate-003:
	uv run maid validate manifests/task-003-behavioral-validation.manifest.json

validate-004:
	uv run maid validate manifests/task-004-behavioral-test-integration.manifest.json

validate-005:
	uv run maid validate manifests/task-005-type-validation.manifest.json

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

type-check:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

type-check-fix:
	uv run ruff check . --fix

format:
	uv run black .

# Dead code detection with vulture
dead-code:
	@echo "🔍 Scanning for unused/dead code..."
	@uv run vulture maid_runner/ tests/ \
		--min-confidence 80 \
		--exclude "*/__pycache__/*" \
		--sort-by-size || true
	@echo ""
	@echo "💡 Note: Review results carefully for false positives"
	@echo "   Add legitimate exceptions to .vulture whitelist file"

# Sync Claude Code integration files for package distribution
sync-claude:
	@echo "Syncing Claude Code integration files..."
	@uv run python scripts/sync_claude_files.py

# Build package (includes sync)
build: sync-claude
	@echo "Building package..."
	@uv run python -m build

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	@rm -rf maid_runner/claude/ dist/ build/ *.egg-info
	@echo "✓ Clean complete"