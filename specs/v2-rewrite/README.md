# MAID Runner v2 Rewrite Specification

This directory contains the complete architectural specification for the MAID Runner v2 rewrite. These documents serve as the **single source of truth** for the implementation.

## How to Use These Specs

### For Autonomous Implementation (New Session)

1. **Read [14-progress-tracker.md](14-progress-tracker.md) FIRST** to determine current state
2. Find the current phase and task from the progress tracker
3. Read the spec document(s) for that task
4. Read [15-golden-tests.md](15-golden-tests.md) for concrete test cases
5. Read [16-porting-reference.md](16-porting-reference.md) when porting algorithms from current code
6. Implement with TDD: write tests from golden cases, then implement to pass
7. Update the progress tracker checkboxes and session state when done

### For Initial Understanding

1. **Start with [00-overview.md](00-overview.md)** for context, principles, and success criteria
2. **Read [01-architecture.md](01-architecture.md)** for the complete package structure and data flow
3. **Follow [12-migration-plan.md](12-migration-plan.md)** for the phased implementation order
4. **Reference individual spec files** during implementation of each module

## Document Index

### Foundation
| Doc | Scope |
|-----|-------|
| [00-overview.md](00-overview.md) | Vision, principles, success criteria, what changes |
| [01-architecture.md](01-architecture.md) | Package structure, layer rules, dependencies, data flow |
| [02-manifest-schema-v2.md](02-manifest-schema-v2.md) | Complete YAML manifest format with examples |
| [03-data-types.md](03-data-types.md) | All enums, dataclasses, and type definitions |

### Core Modules
| Doc | Scope |
|-----|-------|
| [04-core-manifest.md](04-core-manifest.md) | Manifest loading, parsing, chain resolution |
| [05-core-validation.md](05-core-validation.md) | Validation engine (behavioral + implementation) |
| [05a-core-snapshot.md](05a-core-snapshot.md) | Snapshot generation and test stub creation |
| [05b-core-test-runner.md](05b-core-test-runner.md) | Test execution and batch optimization |

### Plugin System
| Doc | Scope |
|-----|-------|
| [06-validators.md](06-validators.md) | BaseValidator ABC, registry, Python/TS/Svelte validators |

### Optional Modules
| Doc | Scope |
|-----|-------|
| [07-graph-module.md](07-graph-module.md) | Knowledge graph: model, builder, query, export |
| [08-coherence-module.md](08-coherence-module.md) | Coherence validation: engine, checks, results |

### Interface Layer
| Doc | Scope |
|-----|-------|
| [09-cli.md](09-cli.md) | CLI commands, arguments, output formatting |
| [10-public-api.md](10-public-api.md) | Library API surface, usage examples, stability guarantees |

### Process
| Doc | Scope |
|-----|-------|
| [11-testing-strategy.md](11-testing-strategy.md) | Test organization, fixtures, patterns, migration |
| [12-migration-plan.md](12-migration-plan.md) | 7-phase migration with acceptance criteria |
| [13-backward-compatibility.md](13-backward-compatibility.md) | V1 JSON manifest support and conversion |

### Autonomous Implementation Support
| Doc | Scope |
|-----|-------|
| [14-progress-tracker.md](14-progress-tracker.md) | Machine-readable progress checklist and session handoff protocol |
| [15-golden-tests.md](15-golden-tests.md) | Concrete input/output test cases for every module |
| [16-porting-reference.md](16-porting-reference.md) | Critical algorithms extracted from current codebase |

## Implementation Order

Per [12-migration-plan.md](12-migration-plan.md):

```
Phase 1: Foundation          (03, 04 partial, 13)
Phase 2: Validation Engine   (04, 05, 05b)
Phase 3: Validators          (06)            ← parallel with Phase 2
Phase 4: CLI Rewrite         (09)
Phase 5: Features            (07, 08, 05a)
Phase 6: Ecosystem           (10)
Phase 7: Cleanup             (-)
```

## Key Design Decisions

1. **Library-first** - CLI is a thin wrapper; ecosystem tools import directly
2. **Multi-file manifests** - One manifest per feature, not per file
3. **YAML-native** - Primary format; JSON v1 supported via compat layer
4. **Plugin validators** - Python always available; TS/Svelte optional
5. **Semantic naming** - Slug-based manifests, domain-organized tests
6. **Frozen data types** - All value objects are immutable dataclasses
