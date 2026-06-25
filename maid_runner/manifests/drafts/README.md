# Draft Manifests

Draft manifests are planning inventory. They stay outside the active
`manifests/*.manifest.yaml` set so normal MAID validation only covers approved
implementation contracts.

Child implementation drafts live at `manifests/drafts/*.manifest.yaml`.
Epic planning records live at `manifests/drafts/*.epic.yaml`.

The canonical workflow guide is
[`docs/draft-manifest-workflow.md`](../../docs/draft-manifest-workflow.md).
Outcome capture guidance is documented in
[`docs/manifest-outcome-records.md`](../../docs/manifest-outcome-records.md).

Use `000-parser-replacement-roadmap.md` as the alignment map for parser
replacement follow-up work, shared boundaries, dependencies, and promotion
order.

Drafts marked with the following comments are epic planning drafts:

```yaml
# draft-kind: epic
# promotion: split-before-promote
```

Do not promote or implement epic drafts directly. Treat them as
split-before-promote inventory: split them into smaller implementation-sized
draft manifests, refine the behavioral tests, and promote one child draft at a
time.

Consumed epics that remain for historical context are marked with:

```yaml
# archive-kind: consumed-draft-epic
metadata:
  status: archived
```

Archived epic files are not live planning inventory. Keep their paths stable
when active manifests still read them, and use their `read` lists only as
pointers to the promoted child manifests or current specialist backlog.

A draft may exist as planning inventory before tests or implementation files are
created. Missing planned test files, `E200`, or pytest "file not found" results
mean the draft is not promotion-ready yet; they are not defects in inventory
drafts by themselves.

A draft is ready to promote when:

- it is not marked as an epic planning draft;
- it is not marked as archived inventory;
- every declared public artifact has an exact signature or field type;
- behavioral tests exist and exercise every declared production artifact;
- the behavioral tests fail against the current implementation for the intended
  reason, unless the draft is explicitly characterization-only;
- `maid validate <draft-path> --mode behavioral` passes;
- the manifest has been reviewed and approved.

Promote one selected child draft with
`uv run maid manifest promote manifests/drafts/<slug>.manifest.yaml`.
Do not manually move or copy draft manifests; the command migrates plan locks,
red evidence, and self-referencing validate paths. For metadata-only reference cleanup on
locked active manifests, use
`uv run maid plan revise <manifest> --reason "<text>" --preserve-red-evidence`.
Compiler-backed work must preserve the fast path unless a manifest explicitly
evolves that contract.

Outcome records are added after a completed implementation review, not during
initial draft planning. Drafts should describe the intended contract; the
promoted manifest's optional `outcome` field records the completed result,
validation evidence, and review notes after the work closes.
