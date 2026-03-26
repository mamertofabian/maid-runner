# MAID Project Export Format

**References:** [18-archspec-translation-layer.md](18-archspec-translation-layer.md)

## Purpose

Defines the complete ZIP export format for the "Export as MAID Project" feature
in ArchSpec. The export should be a self-contained project that an AI agent can
implement without any human setup beyond `unzip` and `pip install`.

## Current State

The MAID export currently produces:
```
project-maid-project.zip
├── .maidrc.yaml
└── manifests/
    ├── feature-*.manifest.yaml
    ├── api-*.manifest.yaml
    └── page-*.manifest.yaml
```

This is missing: reference specs, AI rules, README, and the implementation prompt.

## Target Format

```
project-maid-project.zip
├── IMPLEMENT.md                       # Implementation prompt for AI agents
├── README.md                          # AI-generated project overview (premium)
├── CLAUDE.md                          # AI-generated Claude Code rules (premium)
├── .cursorrules                       # AI-generated Cursor rules (premium)
├── .windsurfrules                     # AI-generated Windsurf rules (premium)
├── .maidrc.yaml                       # MAID configuration
├── specs/                             # ArchSpec reference specifications
│   ├── {project}-basics.md
│   ├── {project}-requirements.md
│   ├── {project}-features.md
│   ├── {project}-pages.md
│   ├── {project}-data-model.md
│   ├── {project}-api-endpoints.md
│   ├── {project}-test-cases.md
│   ├── {project}-ui-design.md
│   └── implementation-prompts.md
├── manifests/                         # MAID v2 contracts
│   ├── feature-*.manifest.yaml
│   ├── api-*.manifest.yaml
│   ├── page-*.manifest.yaml
│   └── test-*.manifest.yaml
└── tests/                             # Acceptance test scaffolds (rigor >= 2)
    └── acceptance/
        └── test_*.py
```

## What Each File Provides

| File | Purpose | Who Reads It | Tier |
|------|---------|-------------|------|
| `IMPLEMENT.md` | Step-by-step implementation instructions for AI agent | AI agent | Free |
| `README.md` | Project overview, goals, features | Human + AI | Premium |
| `CLAUDE.md` | Claude Code persona, rules, constraints | Claude Code | Premium |
| `.cursorrules` | Cursor AI rules | Cursor | Premium |
| `.windsurfrules` | Windsurf AI rules | Windsurf | Premium |
| `.maidrc.yaml` | MAID Runner configuration | MAID Runner | Free |
| `specs/*.md` | Human-readable specifications (reference) | AI + Human | Free |
| `manifests/*.yaml` | Machine-checkable contracts | MAID Runner | Free |
| `tests/acceptance/` | Acceptance test scaffolds | pytest/vitest | Free (rigor >= 2) |

### Free Tier Export

All users get:
- `IMPLEMENT.md` (generated from template)
- `.maidrc.yaml`
- `specs/` (markdown specs they already have)
- `manifests/` (MAID contracts)
- `tests/acceptance/` (if rigor >= 2)

### Premium Tier Export

Premium users additionally get:
- `README.md` (AI-generated, comprehensive)
- `CLAUDE.md` (AI-generated, 1000+ lines of project-specific rules)
- `.cursorrules` (AI-generated)
- `.windsurfrules` (AI-generated)

## IMPLEMENT.md Template

This file is auto-generated for every MAID project export. It's the prompt that
tells an AI agent how to implement the project.

The template uses variables from the project specs:

- `{PROJECT_NAME}` — from project basics
- `{LANGUAGE}` — from tech stack (Python/TypeScript)
- `{FRAMEWORK}` — from tech stack (FastAPI/Express/SvelteKit/etc.)
- `{DATABASE}` — from tech stack (PostgreSQL/MongoDB/etc.)
- `{MANIFEST_COUNT}` — count of manifests in the export
- `{FEATURE_COUNT}` — count of feature manifests
- `{API_COUNT}` — count of API manifests
- `{PAGE_COUNT}` — count of page manifests
- `{PACKAGE_MANAGER}` — uv/npm/pnpm based on language
- `{TEST_RUNNER}` — pytest/vitest based on language
- `{INSTALL_CMD}` — full install command
- `{DEV_DEPS}` — dev dependency install command

### Template Content

See next section for the complete IMPLEMENT.md template.

## Backend Changes Required

In `arch-spec/backend/app/api/routes/project_specs.py`, the `export_maid_project`
endpoint needs to:

1. **Generate IMPLEMENT.md** from the template using project metadata
2. **Include specs/ directory** — generate markdown specs (reuse existing
   markdown generation functions from DownloadAllMarkdown)
3. **Include AI-generated files** if user is premium:
   - Fetch existing CLAUDE.md, README.md from the project's spec exports
   - Or generate them on the fly if not cached
4. **Bundle everything into the ZIP**

```python
# In the ZIP building section, add:

# Add IMPLEMENT.md
implement_md = generate_implement_md(project, project_specs, language, manifest_count)
zf.writestr("IMPLEMENT.md", implement_md)

# Add specs/ (reuse markdown generation)
for spec_name, spec_content in generate_spec_markdowns(project, project_specs):
    zf.writestr(f"specs/{spec_name}", spec_content)

# Add premium files if user has premium plan
if user_is_premium:
    if claude_md := await get_or_generate_claude_md(project_id, database):
        zf.writestr("CLAUDE.md", claude_md)
    if readme_md := await get_or_generate_readme(project_id, database):
        zf.writestr("README.md", readme_md)
    if cursor_rules := await get_or_generate_cursor_rules(project_id, database):
        zf.writestr(".cursorrules", cursor_rules)
    if windsurf_rules := await get_or_generate_windsurf_rules(project_id, database):
        zf.writestr(".windsurfrules", windsurf_rules)
```

## Estimation

| Change | Location | Lines |
|--------|----------|-------|
| IMPLEMENT.md template generator | `maid_exporter.py` or new `implement_template.py` | ~150 |
| Spec markdown bundling | `project_specs.py` endpoint | ~40 |
| Premium file bundling | `project_specs.py` endpoint | ~30 |
| Template variables extraction | `maid_exporter.py` | ~30 |
| **Total** | | **~250** |
