"""Behavioral tests for the 091-01 validation hot-path caches.

Covers three independent caches, and in every case the observable contract is
"same answer, less work". The work is asserted by counting filesystem reads
rather than by timing, so the tests stay deterministic.

Production symbols are imported inside each test so that a missing symbol
produces an ordinary in-test failure rather than a collection error, which MAID
classifies as invalid red evidence.
"""

from pathlib import Path

import pytest
import yaml


MANIFEST_TEMPLATE = """schema: "2"
goal: "{goal}"
type: feature
created: "{created}"
files:
  {section}:
    - path: {path}
      artifacts:
        - kind: function
          name: {func}
validate:
  - pytest tests/ -v
"""


@pytest.fixture()
def chain_dir(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


def _write_manifest(chain_dir, slug, *, path, func, created, section="create"):
    target = chain_dir / f"{slug}.manifest.yaml"
    target.write_text(
        MANIFEST_TEMPLATE.format(
            goal=f"Manifest {slug}",
            created=created,
            path=path,
            func=func,
            section=section,
        )
    )
    return target


def _count_read_text(monkeypatch):
    """Count Path.read_text calls, returning a mutable counter."""
    calls = {"n": 0}
    original = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    return calls


def _make_package(root, package, symbol, *, reexport=True):
    """Create <root>/<package>/__init__.py re-exporting symbol from .impl."""
    pkg = root / package
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "impl.py").write_text(f"def {symbol}():\n    return 1\n")
    body = f"from .impl import {symbol}\n" if reexport else "value = 1\n"
    (pkg / "__init__.py").write_text(body)
    return pkg


class TestManifestYamlLoader:
    def test_duplicate_manifest_keys_are_rejected_on_the_selected_loader(
        self, tmp_path
    ):
        """Duplicate-key rejection is a correctness guarantee, not an optimization.

        It must survive whichever loader the installed pyyaml provides, so this
        pins the behavior independently of which class is selected.
        """
        from maid_runner.core.manifest import ManifestLoadError, load_manifest_raw

        target = tmp_path / "dupe.manifest.yaml"
        target.write_text('schema: "2"\ngoal: first\ngoal: second\n')

        with pytest.raises(ManifestLoadError) as excinfo:
            load_manifest_raw(target)

        assert "duplicate" in str(excinfo.value).lower()

    def test_manifest_parsing_result_is_loader_independent(self, tmp_path):
        """A faster loader must not quietly change manifest semantics."""
        from maid_runner.core.manifest import load_manifest_raw

        source = (
            'schema: "2"\n'
            "goal: |\n"
            "  a block scalar\n"
            "  spanning lines\n"
            "defaults: &defaults\n"
            "  kind: function\n"
            "artifacts:\n"
            "  - <<: *defaults\n"
            "    name: grüßen\n"
            "empty:\n"
            "numbers: [1, 2, 3]\n"
        )
        target = tmp_path / "shapes.manifest.yaml"
        target.write_text(source, encoding="utf-8")

        assert load_manifest_raw(target) == yaml.safe_load(source)


class TestReexportResolutionCache:
    def test_reexport_resolution_is_memoized_within_a_scope(
        self, tmp_path, monkeypatch
    ):
        """Repeated resolution of the same symbol must stop re-reading the file.

        resolve_reexport was measured at 195,925 calls per `maid verify`, each
        doing its own stat and, on a hit, its own read plus ast.parse.
        """
        from maid_runner.core.module_paths import (
            clear_reexport_resolution_cache,
            resolve_reexport,
        )

        _make_package(tmp_path, "pkg", "widget")
        clear_reexport_resolution_cache()

        counter = _count_read_text(monkeypatch)
        first = resolve_reexport("pkg", "widget", tmp_path)
        reads_after_first = counter["n"]
        second = resolve_reexport("pkg", "widget", tmp_path)

        assert first == second
        assert first is not None
        assert reads_after_first >= 1
        assert counter["n"] == reads_after_first

    def test_reexport_cache_clear_observes_changed_source(self, tmp_path):
        """A long-lived process must not serve a stale re-export after an edit."""
        from maid_runner.core.module_paths import (
            clear_reexport_resolution_cache,
            resolve_reexport,
        )

        pkg = _make_package(tmp_path, "pkg", "widget")
        clear_reexport_resolution_cache()

        assert resolve_reexport("pkg", "widget", tmp_path) is not None

        (pkg / "__init__.py").write_text("value = 1\n")
        clear_reexport_resolution_cache()

        assert resolve_reexport("pkg", "widget", tmp_path) is None

    def test_validation_scope_boundary_clears_reexport_cache(self, tmp_path):
        """The cache must be bound to the validation scope, not the process.

        This is the guard that keeps the speedup from becoming a correctness
        regression in a long-lived process such as the daemon: a resolution
        cached inside one scope must not answer a later scope after the source
        changed.
        """
        from maid_runner.core.module_paths import resolve_reexport
        from maid_runner.core.validate import ValidationEngine

        pkg = _make_package(tmp_path, "pkg", "widget")
        engine = ValidationEngine(project_root=tmp_path)

        with engine.validation_cache_scope():
            assert resolve_reexport("pkg", "widget", tmp_path) is not None

        (pkg / "__init__.py").write_text("value = 1\n")

        with engine.validation_cache_scope():
            assert resolve_reexport("pkg", "widget", tmp_path) is None


class TestDaemonHeldScopeInvalidation:
    def test_held_open_scope_observes_barrel_edit_between_requests(self, tmp_path):
        """The daemon holds one scope open for its lifetime, so boundaries never recur.

        DaemonValidationCacheScope enters the outermost validation scope once at
        construction. Every later request runs at depth 1, so the scope-boundary
        clear cannot fire again. Without a per-request clear the daemon answers a
        second request from a re-export resolved before the source changed, and
        reports a PASS for a symbol that is no longer exported.
        """
        from maid_runner.daemon.cache import DaemonValidationCacheScope

        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "impl.py").write_text("def widget():\n    return 1\n")
        (pkg / "__init__.py").write_text("from .impl import widget\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_widget.py").write_text(
            "from pkg import widget\n\n\ndef test_widget():\n    assert widget() == 1\n"
        )

        # The declared artifact lives in pkg/impl.py and the test reaches it
        # through the pkg barrel, so identity matching - not artifact collection -
        # is what consults resolve_reexport. Declaring the barrel itself would
        # miss the defect, because collection is content-addressed and would
        # report the missing symbol before the cached resolution mattered.
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        (manifests / "demo.manifest.yaml").write_text(
            'schema: "2"\n'
            'goal: "Barrel consumer"\n'
            "type: feature\n"
            'created: "2025-06-01T00:00:00Z"\n'
            "files:\n"
            "  create:\n"
            "    - path: pkg/impl.py\n"
            "      artifacts:\n"
            "        - kind: function\n"
            "          name: widget\n"
            "  read:\n"
            "    - tests/test_widget.py\n"
            "validate:\n"
            "  - pytest tests/test_widget.py -v\n"
        )

        cache = DaemonValidationCacheScope(project_root=tmp_path)
        first = cache.validate(
            "manifests/demo.manifest.yaml",
            mode="implementation",
            use_chain=False,
        )
        assert first["success"] is True

        (pkg / "__init__.py").write_text("value = 1\n")

        second = cache.validate(
            "manifests/demo.manifest.yaml",
            mode="implementation",
            use_chain=False,
        )

        assert second["success"] is False
        assert [error["code"] for error in second["errors"]] == ["E200"]


class TestManifestsForFileIndex:
    def test_manifests_for_file_returns_same_manifests_as_a_linear_scan(
        self, chain_dir, tmp_path
    ):
        """Indexed ownership must equal the linear scan it replaces, in order."""
        from maid_runner.core.chain import ManifestChain

        _write_manifest(
            chain_dir,
            "a-first",
            path="src/shared.py",
            func="alpha",
            created="2025-06-01T00:00:00Z",
        )
        _write_manifest(
            chain_dir,
            "b-second",
            path="src/shared.py",
            func="beta",
            created="2025-06-02T00:00:00Z",
        )
        _write_manifest(
            chain_dir,
            "c-other",
            path="src/other.py",
            func="gamma",
            created="2025-06-03T00:00:00Z",
        )

        chain = ManifestChain(chain_dir, project_root=tmp_path)
        expected = [
            m
            for m in chain.active_manifests()
            if "src/shared.py" in m.all_writable_paths
        ]

        assert chain.manifests_for_file("src/shared.py") == expected
        assert [m.slug for m in expected] == ["a-first", "b-second"]

    def test_manifests_for_file_index_is_invalidated_on_reload(
        self, chain_dir, tmp_path
    ):
        """A cached index must not outlive the manifest set it was built from."""
        from maid_runner.core.chain import ManifestChain

        _write_manifest(
            chain_dir,
            "a-first",
            path="src/shared.py",
            func="alpha",
            created="2025-06-01T00:00:00Z",
        )

        chain = ManifestChain(chain_dir, project_root=tmp_path)
        assert [m.slug for m in chain.manifests_for_file("src/shared.py")] == [
            "a-first"
        ]

        _write_manifest(
            chain_dir,
            "b-second",
            path="src/shared.py",
            func="beta",
            created="2025-06-02T00:00:00Z",
        )
        chain.reload()

        assert [m.slug for m in chain.manifests_for_file("src/shared.py")] == [
            "a-first",
            "b-second",
        ]

    def test_read_only_path_still_resolves_to_no_writable_manifest(
        self, chain_dir, tmp_path
    ):
        """The index must not widen writable ownership to read declarations."""
        from maid_runner.core.chain import ManifestChain

        target = chain_dir / "reader.manifest.yaml"
        target.write_text(
            'schema: "2"\n'
            'goal: "Reads only"\n'
            "type: feature\n"
            'created: "2025-06-01T00:00:00Z"\n'
            "files:\n"
            "  create:\n"
            "    - path: src/owned.py\n"
            "      artifacts:\n"
            "        - kind: function\n"
            "          name: owned\n"
            "  read:\n"
            "    - src/context.py\n"
            "validate:\n"
            "  - pytest tests/ -v\n"
        )

        chain = ManifestChain(chain_dir, project_root=tmp_path)

        assert chain.manifests_for_file("src/context.py") == []
        assert [m.slug for m in chain.manifests_for_file("src/owned.py")] == ["reader"]
