"""CLI handler for 'maid validate' command."""

from __future__ import annotations

import argparse
import sys

from maid_runner.cli.commands._format import (
    format_batch_result,
    format_coherence_result,
    format_validation_result,
    print_error,
)


def cmd_validate(args: argparse.Namespace) -> int:
    if args.watch or args.watch_all:
        return _run_watch(args)

    if args.coherence_only:
        return _run_coherence_only(args)

    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")

    try:
        if args.manifest_path:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
            )
            output = format_validation_result(
                result, json_mode=args.json, quiet=args.quiet
            )
            if output:
                print(output)

            if args.coherence and result.success:
                _print_coherence(args)

            return 0 if result.success else 1
        else:
            batch = engine.validate_all(args.manifest_dir, mode=mode)
            print(format_batch_result(batch, json_mode=args.json, quiet=args.quiet))

            if args.coherence and batch.success:
                _print_coherence(args)

            return 0 if batch.success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2


def _run_coherence_only(args: argparse.Namespace) -> int:
    """Run only coherence checks, no structural validation."""
    from pathlib import Path

    from maid_runner.coherence.engine import CoherenceEngine
    from maid_runner.core.chain import ManifestChain

    try:
        chain = ManifestChain(args.manifest_dir)
        engine = CoherenceEngine()
        result = engine.validate(chain, project_root=Path.cwd())
        print(format_coherence_result(result, json_mode=args.json))
        return 0 if result.success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2


def _print_coherence(args: argparse.Namespace) -> None:
    """Run and print coherence checks as an addition to structural validation."""
    from pathlib import Path

    from maid_runner.coherence.engine import CoherenceEngine
    from maid_runner.core.chain import ManifestChain

    try:
        chain = ManifestChain(args.manifest_dir)
        engine = CoherenceEngine()
        result = engine.validate(chain, project_root=Path.cwd())
        print()
        print(format_coherence_result(result, json_mode=args.json))
    except Exception:
        pass  # Coherence is best-effort when used as --coherence flag


def _run_watch(args: argparse.Namespace) -> int:
    """Run validation in watch mode."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print(
            "Error: Watch mode requires watchdog. "
            "Install with: pip install maid-runner[watch]",
            file=sys.stderr,
        )
        return 2

    import time

    class _Handler(FileSystemEventHandler):
        def __init__(self) -> None:
            self.triggered = False

        def on_modified(self, event) -> None:  # type: ignore[override]
            if not event.is_directory and event.src_path.endswith(
                (".py", ".ts", ".tsx", ".svelte", ".yaml", ".json")
            ):
                self.triggered = True

    handler = _Handler()
    observer = Observer()

    # Determine paths to watch
    from pathlib import Path

    watch_paths = [Path(args.manifest_dir)]
    if args.manifest_path and not args.watch_all:
        # Single-manifest watch: also watch files referenced by the manifest
        try:
            from maid_runner.core.manifest import load_manifest

            m = load_manifest(args.manifest_path)
            for fs in m.all_file_specs:
                p = Path(fs.path).parent
                if p.exists():
                    watch_paths.append(p)
        except Exception:
            pass
    else:
        # Watch-all: watch common source directories
        for d in [Path("maid_runner"), Path("src"), Path(".")]:
            if d.is_dir():
                watch_paths.append(d)
                break

    for p in watch_paths:
        if p.exists():
            observer.schedule(handler, str(p), recursive=True)

    observer.start()
    print("Watching for changes... (Ctrl+C to stop)")

    try:
        # Initial run
        _run_validation_pass(args)
        while True:
            time.sleep(0.5)
            if handler.triggered:
                handler.triggered = False
                time.sleep(0.2)  # Debounce
                print("\n--- Change detected, re-validating ---\n")
                _run_validation_pass(args)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopped watching.")
    observer.join()
    return 0


def _run_validation_pass(args: argparse.Namespace) -> None:
    """Run a single validation pass (used by watch mode)."""
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")

    try:
        if args.manifest_path and not args.watch_all:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
            )
            output = format_validation_result(
                result, json_mode=args.json, quiet=args.quiet
            )
            if output:
                print(output)
        else:
            batch = engine.validate_all(args.manifest_dir, mode=mode)
            print(format_batch_result(batch, json_mode=args.json, quiet=args.quiet))
    except Exception as e:
        print_error(str(e), json_mode=args.json)
