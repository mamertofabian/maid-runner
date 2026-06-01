# GitHub Actions

<!-- _github_actions_setup_guide -->

MAID Runner ships reusable GitHub Actions workflow templates for repositories
that want CI gates around manifest validation, manifest-declared tests, and
coverage reporting. The templates can run directly in this repository on
`pull_request` and `push`, or downstream projects can call them through
`workflow_call`.

## Validation Gate

Use the validation template when a pull request or push should prove that the
active manifest chain, file-tracking checks, changed-scope checks, and declared
tests still hold.

```yaml
name: MAID Validation

on:
  pull_request:
  push:
    branches: [main]

jobs:
  maid-validation:
    uses: mamertofabian/maid-runner/.github/workflows/maid-validation.yml@main
    with:
      python-version: "3.12"
      install-command: uv sync --group dev
      manifest-dir: manifests/
      test-jobs: 2
```

For `pull_request` runs, the template fetches the base branch and runs
`maid verify --base-ref origin/<base> --json`. That explicit base ref is
important in CI because changed-scope validation should compare the pull
request against the branch it targets, not against whatever local Git metadata
happens to be available.

For direct `push` runs, the template runs the full repository gate with
`--no-changed-scope`. Push validation should validate all active manifests
without requiring a pull-request base branch.

If a caller needs a custom comparison base, pass `base-ref`:

```yaml
jobs:
  maid-validation:
    uses: mamertofabian/maid-runner/.github/workflows/maid-validation.yml@main
    with:
      base-ref: origin/dev
```

The workflow writes `.maid/maid-verify.json`, uploads it as the
`maid-verify-report` artifact, and appends a concise status block to
`$GITHUB_STEP_SUMMARY`. A non-zero `maid verify` exit code fails the job, so the
workflow can be used as a PR validation gate.

## Test And Coverage Gate

Use the test template when CI should run the manifest-declared test commands
and then publish a conventional coverage report.

```yaml
name: MAID Test

on:
  pull_request:
  push:
    branches: [main]

jobs:
  maid-test:
    uses: mamertofabian/maid-runner/.github/workflows/maid-test.yml@main
    with:
      python-version: "3.12"
      install-command: uv sync --group dev
      manifest-dir: manifests/
      test-jobs: 2
      coverage-command: uv run python -m pytest tests/ --cov --cov-report=xml
```

The template runs `maid test --json` before coverage. This keeps MAID's
manifest-declared test contract as the gate and treats coverage as a separate,
overridable reporting command. Set `coverage-command` to the command your
project already uses, or leave the default when `pytest-cov` is available.

The workflow writes `.maid/maid-test.json`, uploads it as the `maid-test-report`
artifact, uploads `coverage.xml` as the `coverage-report` artifact when present,
and appends the MAID test status to `$GITHUB_STEP_SUMMARY`.

The examples use `@main` because this repository publishes exact release tags
such as `v2.16.0`, not a moving `v2` major tag. Pin to an exact release tag
after the templates are released if your project needs immutable CI behavior.

## Inputs

Both templates accept:

- `python-version`: Python version installed by `actions/setup-python`.
- `install-command`: Dependency installation command, usually `uv sync` or
  `uv sync --group dev`.
- `manifest-dir`: Manifest directory passed to MAID.
- `test-jobs`: Parallel MAID test jobs.

`maid-validation.yml` also accepts:

- `base-ref`: Explicit comparison base for `maid verify --base-ref`.
- `extra-verify-args`: Extra flags for local policy, such as `--advisory`.

`maid-test.yml` also accepts:

- `coverage-command`: Follow-up coverage command run after `maid test --json`.
