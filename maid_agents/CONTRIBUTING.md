# Contributing to MAID Agents

🎉 **Thank you for your interest in contributing to MAID Agents!**

MAID Agents is a Claude Code automation layer for the MAID (Manifest-driven AI Development) methodology. We welcome contributions from the community!

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) for dependency management
- `maid-runner` package installed (external dependency)

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/maid-agents.git
cd maid-agents

# Install package in editable mode
uv pip install -e .

# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
uv run python -m pytest tests/ -v
```

## 📝 How to Contribute

### Reporting Bugs

If you find a bug:

1. Check if it's already reported in [Issues](https://github.com/YOUR_ORG/maid-agents/issues)
2. If not, open a new issue with:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version, maid-runner version)

### Suggesting Features

We love feature ideas! Before suggesting:

1. Open an issue with the `enhancement` label
2. Describe the use case and why it's valuable
3. Explain how it fits into the MAID workflow

### Submitting Code

#### Before You Start

- For small fixes (typos, bugs): just open a PR
- For new features: open an issue first to discuss

#### Development Workflow

1. **Fork the repository**

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Write clear, focused commits
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation as needed

4. **Run quality checks**
   ```bash
   # Format code
   make format

   # Lint
   make lint

   # Run tests
   make test

   # Validate manifests
   make validate
   ```

5. **Commit using conventional commits**
   ```bash
   git commit -m "feat: add support for new agent type"
   git commit -m "fix: handle timeout errors in Claude wrapper"
   git commit -m "docs: update README with new examples"
   ```

6. **Push and open a Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```

#### Pull Request Guidelines

- **Title**: Use conventional commit format (`feat:`, `fix:`, `docs:`, etc.)
- **Description**: Explain what and why
- **Link issues**: Use `Fixes #123` or `Closes #456`
- **Tests**: All tests must pass
- **Documentation**: Update docs if you change behavior

## 🏗️ Project Structure

```
maid-agents/
├── docs/                    # Documentation and specifications
├── manifests/               # Task manifests (chronological)
├── tests/                   # Test suite
├── maid_agents/            # Main package
│   ├── agents/             # Agent implementations
│   ├── claude/              # Claude Code integration
│   ├── cli/                 # CLI entry point
│   ├── config/              # Configuration
│   ├── core/                # Core orchestration
│   └── utils/               # Utilities
└── examples/                # Example usage
```

## 📚 Code Style

We use:
- **Black** for formatting (line length: 88)
- **Ruff** for linting
- **Type hints** for all public APIs
- **Docstrings** for public functions/classes

### Example

```python
def create_manifest(
    goal: str,
    editable_files: list[str]
) -> dict[str, Any]:
    """
    Create a MAID manifest from a goal.

    Args:
        goal: High-level description of the task
        editable_files: List of files to edit

    Returns:
        Manifest dictionary with goal and file specifications

    Raises:
        ValueError: If goal is empty
    """
    # Implementation
```

## 🧪 Testing

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_task_XXX_*.py` following MAID conventions
- Use descriptive test names: `test_manifest_architect_creates_valid_manifest()`
- Test both success and failure cases
- Use fixtures for common setup
- Follow the unit testing rules in `docs/unit-testing-rules.md`

### Running Tests

```bash
# All tests
make test

# Specific test file
uv run python -m pytest tests/test_task_001_orchestrator_skeleton.py -v

# With coverage
uv run python -m pytest tests/ --cov=maid_agents --cov-report=html
```

## 📖 MAID Methodology

This project follows the MAID (Manifest-driven AI Development) methodology. Key principles:

1. **Explicitness over Implicitness**: All changes are explicitly declared in manifests
2. **Test-Driven Validation**: Tests define success criteria
3. **Verifiable Chronology**: Every change is tracked via manifest history

See [docs/maid_specs.md](docs/maid_specs.md) for full methodology.

## 🔧 Development Commands

```bash
make help          # Show all available commands
make test          # Run all tests
make validate      # Validate all manifests
make lint          # Run linting
make format        # Format code
make install       # Install package in editable mode
make install-dev   # Install with development dependencies
```

## 🤝 Code of Conduct

Be respectful, constructive, and collaborative. We're building this to enable better AI-assisted development.

## 💬 Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Questions?** Open an issue!

Thank you for making MAID Agents better! 🙌

