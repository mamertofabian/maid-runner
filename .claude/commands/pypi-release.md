---
allowed-tools: Bash(git:*), Bash(python:*), Bash(uv:*), Bash(make:*), Bash(gh:*), Bash(rm:*), Bash(ls:*), Bash(tar:*), Bash(unzip:*), Bash(sleep:*), Edit, Read, TodoWrite, WebFetch
argument-hint: [version-type: patch|minor|major]
description: Prepare and publish a new PyPI release (project)
---

# PyPI Release Automation

Automate the complete PyPI release process including version bumping, changelog updates, building, and publishing via GitHub Actions.

## Your Task

Prepare and publish a new PyPI release for this project. Follow these steps:

1. **Determine Version Number**
   - Read current version from `pyproject.toml`
   - Check recent commits since last release: `git log --oneline -20`
   - Determine version bump type: $ARGUMENTS (default: patch)
     - **patch** (0.1.2 → 0.1.3): Bug fixes, documentation, minor changes
     - **minor** (0.1.2 → 0.2.0): New features, backward-compatible
     - **major** (0.1.2 → 1.0.0): Breaking changes
   - Calculate new version number

2. **Run Code Quality Checks**
   - Run all quality checks FIRST:
     ```bash
     make lint        # Fix any linting errors first
     make format      # Format code
     make test        # Run all tests - MUST PASS
     ```
   - If any checks fail, STOP and report errors to user
   - Use `TodoWrite` to track progress

3. **Update Version and Changelog**
   - Update version in `pyproject.toml`
   - Update `CHANGELOG.md`:
     - Add new version section with today's date (2025-11-29 format)
     - Categorize changes under: Fixed, Added, Changed, Removed
     - Update comparison links at bottom
   - Review git commits to write accurate changelog entries

4. **Build Distribution Packages**
   - Clean old artifacts: `rm -rf dist/ build/ *.egg-info`
   - Build packages: `python -m build`
   - Verify artifacts: `ls -lh dist/`
   - Check contents: `tar -tzf dist/*.tar.gz | head -30`
   - Validate with twine: `python -m twine check dist/*`

5. **Automated Release via GitHub Actions**
   - Stage and commit changes with descriptive title:
     ```bash
     git add pyproject.toml CHANGELOG.md
     # Parse the changelog to extract the main feature/change for this version
     # Use a descriptive title that summarizes what's in the release
     git commit -m "release: vX.Y.Z - [Main feature from changelog]

     - [Summary of key changes]
     - [One-line descriptions from changelog]"

     # Examples of good commit titles:
     # "release: v0.3.0 - File deletion tracking with status field"
     # "release: v0.2.0 - TypeScript/JavaScript support"
     # "release: v0.1.3 - Async function detection fix"
     ```
   - Push to main: `git push origin main`
   - Create and push version tag:
     ```bash
     git tag vX.Y.Z
     git push origin vX.Y.Z
     ```
   - Monitor GitHub Actions workflow:
     ```bash
     gh run list --limit 2
     sleep 60 && gh run list --limit 2
     ```

6. **Verify Release**
   - Check GitHub release: `gh release view vX.Y.Z`
   - Verify PyPI publication: `WebFetch` to https://pypi.org/project/maid-runner/
   - Confirm artifacts include Sigstore signatures

## Important Notes

- **NEVER skip tests**: All tests must pass before releasing
- **Version format**: Use semantic versioning (MAJOR.MINOR.PATCH)
- **Changelog format**: Follow [Keep a Changelog](https://keepachangelog.com/)
- **GitHub Actions**: The workflow automatically publishes to PyPI on version tags
- **Artifacts**: GitHub Actions signs artifacts with Sigstore for security

## Expected Outcomes

1. ✅ Version bumped in `pyproject.toml`
2. ✅ Changelog updated with release notes
3. ✅ All tests passing
4. ✅ Distribution packages built and validated
5. ✅ Git commit and tag created
6. ✅ GitHub Actions workflow triggered
7. ✅ Package published to PyPI
8. ✅ GitHub release created with signed artifacts

## Error Handling

If any step fails:
- **Tests fail**: Fix issues before continuing
- **Build fails**: Check pyproject.toml configuration
- **GitHub Actions fails**: Check workflow logs with `gh run view`
- **PyPI publish fails**: Verify PyPI token is configured in GitHub secrets

Report any errors to the user with specific failure details and suggested fixes.
