# CI/CD Integration

<!-- _ci_cd_integration_guide -->

Use this guide to wire MAID Runner into CI systems as a repeatable handoff
gate. The recommended shape is the same across platforms:

1. Check out enough Git history to resolve the comparison base.
2. Install project dependencies.
3. Run `maid verify` with an explicit base ref for pull requests or merge
   requests.
4. Run `maid test --json` as the manifest-declared contract gate.
5. Upload `.maid/` JSON reports and optional coverage output as build
   artifacts.

For GitHub Actions reusable workflow templates, use the dedicated
[`docs/github-actions.md`](github-actions.md) guide. The examples below
show the same contract in portable pipeline snippets.

## GitHub Actions

The preferred GitHub setup is to call the reusable workflows documented in
[`docs/github-actions.md`](github-actions.md). Use
`.github/workflows/maid-validation.yml` for the validation gate and
`.github/workflows/maid-test.yml` for manifest-declared tests plus coverage.

```yaml
name: MAID CI

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

  maid-test:
    uses: mamertofabian/maid-runner/.github/workflows/maid-test.yml@main
    with:
      python-version: "3.12"
      install-command: uv sync --group dev
      manifest-dir: manifests/
      test-jobs: 2
      coverage-command: uv run python -m pytest tests/ --cov --cov-report=xml
```

The reusable validation workflow writes `.maid/maid-verify.json`, and the test
workflow writes `.maid/maid-test.json` and uploads `coverage.xml` when present.
Pin MAID Runner and workflow references to exact release tags after the
templates are released when your repository needs immutable CI behavior.

## SARIF Platform Consumption

<!-- _sarif_platform_consumption_guidance -->

MAID can also write SARIF 2.1.0 reports for CI systems that render or publish
static-analysis findings. Use `uv run maid validate --sarif .maid/maid.sarif`
or `uv run maid verify --sarif .maid/maid-verify.sarif` beside the existing
JSON commands. The report is written on both pass and fail. CI uploads can run unconditionally, and successful SARIF report generation never changes validation or verification gate exit codes.
Keep the command exit code as the primary gate. The `--json` output remains the canonical machine contract; SARIF is a derived review-time view.

If a requested SARIF path cannot be written, MAID reports that output failure
visibly instead of silently falling back. Identical validation results produce
byte-identical SARIF because run-level timestamps are omitted and results are
sorted by file path, line, and code.

GitHub-specific code scanning upload setup lives in
[`docs/github-actions.md`](github-actions.md). The guidance below covers GitLab,
Jenkins warnings-ng, and generic pipelines.

| MAID diagnostics | SARIF level | Rule ids | Recommended gate |
| --- | --- | --- | --- |
| error diagnostics -> SARIF level `error` | `error` | E1xx chain, E2xx command integrity, E3xx implementation, and other registered error rules | Block the stage through the MAID command exit code; optional SARIF consumers may also fail on `error` results. |
| warnings -> `warning` | `warning` | Registered warning rules from the diagnostics registry | Surface in merge request or build review, but do not treat as the primary pass/fail gate unless your local policy requires it. |
| advisory/info -> `note` | `note` | Registered info/advisory rules from the diagnostics registry | Inform reviewers without blocking. |

SARIF `ruleId` values are MAID E-codes. Rule metadata comes from
`maid_runner/core/diagnostics_registry.py`, and help links point into
[`docs/troubleshooting.md`](troubleshooting.md). The registry stores internal
MAID severities as `error`, `warning`, and `info`; the SARIF serializer maps
internal `info` to SARIF `note`.

### GitLab SARIF Conversion

GitLab does not natively render SARIF. Convert the MAID SARIF report to either
GitLab code quality or SAST JSON, then publish that converted file as a
`codequality` or `sast` artifact so findings can annotate merge requests. The
conversion command depends on the converter you standardize on; keep it pinned
in your project rather than relying on an unversioned global tool.

```yaml
# .gitlab-ci.yml
maid:sarif:
  image: python:3.12
  stage: validate
  before_script:
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="$HOME/.local/bin:$PATH"
    - uv sync --group dev
    - mkdir -p .maid
  script:
    - uv run maid validate --sarif .maid/maid-validate.sarif
    - uv run maid verify --base-ref "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-main}" --sarif .maid/maid-verify.sarif
  after_script:
    - ./ci/convert-maid-sarif-to-gitlab-codequality .maid/maid-verify.sarif > .maid/gl-code-quality-report.json
  artifacts:
    when: always
    paths:
      - .maid/maid-validate.sarif
      - .maid/maid-verify.sarif
      - .maid/gl-code-quality-report.json
    reports:
      codequality: .maid/gl-code-quality-report.json
```

For SAST dashboards, convert to GitLab's SAST report schema and publish it under
`artifacts:reports:sast` instead. Keep the MAID command exit code as the job
gate; the converted report is for review visibility.

### Jenkins SARIF Publishing

The Jenkins warnings-ng plugin consumes SARIF directly. Write the report with
`--sarif`, then record it in a `post { always { ... } }` block so failed MAID
validation still publishes findings.

```groovy
// Jenkinsfile
pipeline {
  agent any

  stages {
    stage('MAID verify') {
      steps {
        sh '''
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.local/bin:$PATH"
          uv sync --group dev
          mkdir -p .maid
          BASE_BRANCH="${CHANGE_TARGET:-main}"
          git fetch --no-tags --depth=1 origin "$BASE_BRANCH"
          uv run maid verify --base-ref "origin/$BASE_BRANCH" --sarif .maid/maid-verify.sarif
        '''
      }
    }
  }

  post {
    always {
      recordIssues tools: [sarif(pattern: '.maid/maid-verify.sarif')]
      archiveArtifacts artifacts: '.maid/maid-verify.sarif', allowEmptyArchive: true
    }
  }
}
```

### Generic Pipelines

For generic pipelines, the report is plain JSON conforming to SARIF 2.1.0. Gate
primarily on the MAID command exit code. Use SARIF checks only as additional
policy, for example when a platform upload step succeeds but you also want an
explicit result-level assertion:

```bash
mkdir -p .maid
uv run maid verify --base-ref "${MAID_BASE_REF:-origin/main}" --sarif .maid/maid-verify.sarif

if jq -e '.runs[].results[]? | select(.level == "error")' .maid/maid-verify.sarif >/dev/null; then
  echo "MAID SARIF contains error-level results"
  exit 1
fi
```

That `jq` check is a secondary policy guard. Prefer `maid verify --json` or
`maid validate --json` when another tool needs a stable machine-readable MAID
contract instead of review annotations.

## GitLab CI

GitLab merge request pipelines expose the target branch through
`CI_MERGE_REQUEST_TARGET_BRANCH_NAME`. Fetch that branch explicitly so
changed-scope validation compares against a real base ref.

```yaml
# .gitlab-ci.yml
stages:
  - validate
  - test

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

maid:verify:
  image: python:3.12
  stage: validate
  before_script:
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="$HOME/.local/bin:$PATH"
    - uv sync --group dev
    - mkdir -p .maid
  script:
    - |
      if [ -n "${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-}" ]; then
        git fetch --no-tags --depth=1 origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
        uv run maid verify --base-ref "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME" --json > .maid/maid-verify.json
      else
        uv run maid verify --no-changed-scope --json > .maid/maid-verify.json
      fi
  artifacts:
    when: always
    paths:
      - .maid/maid-verify.json

maid:test:
  image: python:3.12
  stage: test
  before_script:
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="$HOME/.local/bin:$PATH"
    - uv sync --group dev
    - mkdir -p .maid
  script:
    - uv run maid test --json > .maid/maid-test.json
    - uv run python -m pytest tests/ --cov --cov-report=xml
  artifacts:
    when: always
    paths:
      - .maid/maid-test.json
      - coverage.xml
```

For branch pipelines that do not have a merge request target, the example runs a
full gate with `uv run maid verify --no-changed-scope --json`. If your branch
pipeline has a known release baseline, replace that fallback with an explicit
`--base-ref`.

## Jenkins

In multibranch Jenkins jobs, use the pull request target branch when it is
available and fall back to the main branch for branch builds. Keep the MAID JSON
reports as archived artifacts even when the build fails.

```groovy
// Jenkinsfile
pipeline {
  agent any

  environment {
    BASE_BRANCH = "${env.CHANGE_TARGET ?: 'main'}"
  }

  stages {
    stage('Install') {
      steps {
        sh '''
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.local/bin:$PATH"
          uv sync --group dev
          mkdir -p .maid
        '''
      }
    }

    stage('MAID verify') {
      steps {
        sh '''
          export PATH="$HOME/.local/bin:$PATH"
          git fetch --no-tags --depth=1 origin "$BASE_BRANCH"
          uv run maid verify --base-ref "origin/$BASE_BRANCH" --json > .maid/maid-verify.json
        '''
      }
    }

    stage('MAID test') {
      steps {
        sh '''
          export PATH="$HOME/.local/bin:$PATH"
          uv run maid test --json > .maid/maid-test.json
          uv run python -m pytest tests/ --cov --cov-report=xml
        '''
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: '.maid/maid-verify.json,.maid/maid-test.json,coverage.xml', allowEmptyArchive: true
    }
  }
}
```

Jenkins environments vary widely. If your job uses shallow clones, make the
fetch depth large enough for `git merge-base` to resolve the target branch.

## CircleCI

CircleCI does not always expose pull request metadata consistently across
providers, so set a project environment variable such as `MAID_BASE_REF=main`
or derive it in a setup step for your workflow.

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  maid:
    docker:
      - image: cimg/python:3.12
    steps:
      - checkout
      - run:
          name: Install dependencies
          command: |
            curl -LsSf https://astral.sh/uv/install.sh | sh
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$BASH_ENV"
            source "$BASH_ENV"
            uv sync --group dev
            mkdir -p .maid
      - run:
          name: MAID verify
          command: |
            source "$BASH_ENV"
            git fetch --no-tags --depth=1 origin "${MAID_BASE_REF:-main}"
            uv run maid verify --base-ref "origin/${MAID_BASE_REF:-main}" --json > .maid/maid-verify.json
      - run:
          name: MAID test and coverage
          command: |
            source "$BASH_ENV"
            uv run maid test --json > .maid/maid-test.json
            uv run python -m pytest tests/ --cov --cov-report=xml
      - store_artifacts:
          path: .maid/maid-verify.json
      - store_artifacts:
          path: .maid/maid-test.json
      - store_artifacts:
          path: coverage.xml

workflows:
  maid:
    jobs:
      - maid
```

If CircleCI runs only trusted branch builds, replace the `--base-ref` command
with `uv run maid verify --no-changed-scope --json` to validate the full active
manifest chain.

## Generic CI/CD Template

Use this shell template for systems such as Buildkite, Azure Pipelines,
TeamCity, Drone, or local release scripts.

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${MAID_BASE_REF:-origin/main}"
mkdir -p .maid

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv sync --group dev

git fetch --no-tags --depth=1 origin "${BASE_REF#origin/}"
uv run maid verify --base-ref "$BASE_REF" --json > .maid/maid-verify.json

uv run maid test --json > .maid/maid-test.json
uv run python -m pytest tests/ --cov --cov-report=xml

# Publish these paths with your CI provider's artifact uploader:
# .maid/maid-verify.json
# .maid/maid-test.json
# coverage.xml
```

When your CI provider has separate pull-request and push jobs, use `--base-ref`
for pull requests and `--no-changed-scope` for trusted push builds that should
validate all active manifests.

## Troubleshooting

- Base ref failures: If CI reports that a base ref cannot be resolved, fetch the
  target branch explicitly before `maid verify --base-ref`. Shallow clones often
  need an extra `git fetch --depth=1 origin <target>`.
- Dependency installation failures: Confirm `uv` is added through
  `$HOME/.local/bin` after running Astral's installer, then run
  `uv sync --group dev` from the repository root.
- JSON artifacts are missing: Create `.maid/` before running MAID commands,
  redirect `--json` output to `.maid/maid-verify.json` and
  `.maid/maid-test.json`, and configure the CI provider to upload artifacts
  even on failed jobs.
- Command integrity failures: `E230` means a manifest declares tests that the
  validate command does not run. Keep the manifest `validate` command aligned
  with the full behavioral test file, not a narrow selector.
- Validator warnings: `E307` means MAID has no structural validator for a file
  type such as markdown or YAML. Keep the warning visible in CI output and back
  those files with focused behavioral tests.

For broader diagnostics, see [`docs/troubleshooting.md`](troubleshooting.md).

## Best Practices

- pin MAID Runner and CI workflow references to exact released versions for
  release branches or regulated repositories.
- run `maid verify` before `maid test` so structural, scope, and changed-file
  gates fail before the heavier manifest-declared test run.
- upload `.maid/maid-verify.json` and `.maid/maid-test.json` on every CI run,
  including failed runs.
- preserve `maid test --json` as the contract gate and treat coverage as an
  additional reporting step, not as a substitute for MAID's declared tests.
- Keep pull-request jobs explicit about their base ref. Do not depend on local
  Git metadata in ephemeral CI checkouts.
- Keep push jobs intentional: use `--no-changed-scope` for full active-manifest
  validation, or supply a known release baseline with `--base-ref`.
