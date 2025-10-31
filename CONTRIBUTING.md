# Contributing to MAID Runner

🎉 **Thank you for your interest in contributing to MAID Runner!**

This project is being built in public as part of a YouTube video series. We welcome contributions from the community!

## 🎬 Building in Public

MAID Runner is being developed transparently on YouTube. Each episode covers specific tasks and features:

- 📺 [YouTube Series Playlist](YOUR_YOUTUBE_PLAYLIST_LINK)
- 📖 [Series Outline & Roadmap](/docs/VIDEO_SERIES_ROADMAP.md)

If you're contributing code related to an upcoming episode, please coordinate with us first to avoid conflicts.

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) for dependency management

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/maid-runner.git
cd maid-runner

# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev

# Run tests
uv run python -m pytest tests/ -v
```

## 📝 How to Contribute

### Reporting Bugs

If you find a bug:

1. Check if it's already reported in [Issues](https://github.com/YOUR_ORG/maid-runner/issues)
2. If not, open a new issue with:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version)

### Suggesting Features

We love feature ideas! Before suggesting:

1. Check the [Roadmap](/docs/ROADMAP.md) - it might be planned
2. Open an issue with the `enhancement` label
3. Describe the use case and why it's valuable

### Submitting Code

#### Before You Start

- For small fixes (typos, bugs): just open a PR
- For new features: open an issue first to discuss
- Check if the feature is covered in an upcoming video episode

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
   uv run black .

   # Lint
   uv run ruff check .

   # Run tests
   uv run python -m pytest tests/ -v

   # Type check (optional but recommended)
   uv run mypy validators/
   ```

5. **Commit using conventional commits**
   ```bash
   git commit -m "feat: add support for async validation"
   git commit -m "fix: handle None return types in AST parser"
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
maid-runner/
├── docs/               # Documentation and specifications
├── manifests/          # Task manifests (chronological)
├── tests/              # Test suite
│   ├── validators/     # Validator-specific tests
│   └── test_*.py       # Integration tests
├── validators/         # Core validation logic
│   ├── manifest_validator.py
│   ├── types.py
│   └── schemas/        # JSON schemas
└── .claude/            # Claude Code configuration
```

## 📚 Code Style

We use:
- **Black** for formatting (line length: 88)
- **Ruff** for linting
- **Type hints** for all public APIs
- **Docstrings** for public functions/classes

### Example

```python
def validate_manifest(
    manifest_path: str,
    schema_path: str
) -> ValidationResult:
    """
    Validate a manifest file against its schema.

    Args:
        manifest_path: Path to the manifest JSON file
        schema_path: Path to the JSON schema file

    Returns:
        ValidationResult with status and any errors

    Raises:
        ValidationError: If manifest is invalid
    """
    # Implementation
```

## 🧪 Testing

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Use descriptive test names: `test_detects_missing_function()`
- Test both success and failure cases
- Use fixtures for common setup

### Running Tests

```bash
# All tests
uv run python -m pytest tests/ -v

# Specific test file
uv run python -m pytest tests/test_validate_schema.py -v

# With coverage
uv run python -m pytest tests/ --cov=validators --cov-report=html
```

## 📖 MAID Methodology

This project follows the MAID (Manifest-driven AI Development) methodology it implements. Key principles:

1. **Explicitness over Implicitness**: All changes are explicitly declared in manifests
2. **Test-Driven Validation**: Tests define success criteria
3. **Verifiable Chronology**: Every change is tracked via manifest history

See [docs/maid_specs.md](docs/maid_specs.md) for full methodology.

## 🎥 Video Series Contributions

If you want to contribute something that will be featured in an episode:

1. Check the [Video Series Roadmap](/docs/VIDEO_SERIES_ROADMAP.md)
2. Coordinate in the related GitHub issue
3. We'll feature community contributions in special episodes!

## 🤝 Code of Conduct

Be respectful, constructive, and collaborative. We're building this in public to learn together.

## 💬 Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **YouTube Comments**: Episode-specific questions

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Questions?** Open an issue or reach out via YouTube!

Thank you for making MAID Runner better! 🙌
