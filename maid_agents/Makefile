# MAID Agents Development Makefile
# Convenience commands for development workflow

.PHONY: help test validate install-dev lint format

help:
	@echo "MAID Agents Development Commands:"
	@echo "  make test          - Run all tests"
	@echo "  make validate      - Validate all manifests"
	@echo "  make install-dev   - Install development dependencies"
	@echo "  make lint          - Run linting"
	@echo "  make format        - Format code"
	@echo "  make install       - Install package in editable mode"

# Run all tests
test:
	uv run python -m pytest tests/ -v

# Validate all manifests
validate:
	@for manifest in manifests/task-*.manifest.json; do \
		echo "Validating $$manifest..."; \
		uv run maid validate $$manifest --quiet --use-manifest-chain || exit 1; \
	done
	@echo "✅ All manifests valid"

# Install package in editable mode
install:
	uv pip install -e .

# Install development dependencies
install-dev:
	uv pip install -e ".[dev]"

# Code quality checks
lint:
	uv run ruff check maid_agents/ tests/

lint-fix:
	uv run ruff check maid_agents/ tests/ --fix

format:
	uv run black maid_agents/ tests/

