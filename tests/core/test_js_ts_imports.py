"""Tests for JavaScript and TypeScript required-import scanning."""

from maid_runner.core._js_ts_imports import (
    collect_import_module_bindings,
    collect_import_modules,
    collect_required_imports,
    import_may_satisfy_required,
)


def test_collect_required_imports_ignores_commented_out_imports() -> None:
    source = """
// import { Budget } from "../models/Budget";
import type { Account } from "../models/Account";
"""

    assert "Budget" not in collect_required_imports(source, "src/pages/BudgetPage.ts")
    assert "../models/Budget" not in collect_required_imports(
        source, "src/pages/BudgetPage.ts"
    )
    assert "Account" in collect_required_imports(source, "src/pages/BudgetPage.ts")
    assert "../models/Account" in collect_required_imports(
        source, "src/pages/BudgetPage.ts"
    )


def test_collect_import_modules_keeps_dynamic_import_and_require_resolve() -> None:
    source = """
export async function loadBudget() {
  await import("../models/Budget");
  return require.resolve("../models/Account");
}
"""

    assert collect_import_modules(source, "src/loaders/loadBudget.ts") == {
        "../models/Budget",
        "../models/Account",
    }


def test_collect_import_module_bindings_records_source_names() -> None:
    source = """
import DefaultBudget from "../models/defaultBudget";
import { Budget as BudgetModel, type Account } from "../models/Budget";
import * as Ledger from "../models/Ledger";
export { Report as BudgetReport } from "../models/Report";
"""

    assert collect_import_module_bindings(source, "src/pages/BudgetPage.ts") == {
        "../models/defaultBudget": {"DefaultBudget"},
        "../models/Budget": {"Budget", "Account"},
        "../models/Ledger": {"Ledger"},
        "../models/Report": {"Report"},
    }


def test_import_may_satisfy_required_uses_specifier_parts_and_bindings() -> None:
    unresolved = {"src/models/Budget", "src/finance/Account"}

    assert import_may_satisfy_required("@app/models", unresolved, {"Ignored"})
    assert import_may_satisfy_required("@design/system", unresolved, {"Account"})
    assert not import_may_satisfy_required("@design/system", unresolved, {"Button"})
