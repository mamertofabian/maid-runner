"""Cargo target adapters; Rust syntax remains owned by validator plugins."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import subprocess

from maid_runner.validators.registry import UnsupportedLanguageError, ValidatorRegistry


def _cargo_package_matches(package: dict, specification: str) -> bool:
    if specification == package["id"]:
        return True
    if "://" in specification:
        return False
    name, separator, version = specification.rpartition("@")
    if not separator:
        name, separator, version = specification.rpartition(":")
    if not separator:
        return fnmatch.fnmatchcase(package["name"], specification)
    return fnmatch.fnmatchcase(package["name"], name) and package["version"] == version


def _default_cargo_features(package: dict) -> set[str]:
    features = package.get("features", {})
    enabled: set[str] = set()
    pending = ["default"] if "default" in features else []
    while pending:
        feature = pending.pop()
        if feature in enabled:
            continue
        enabled.add(feature)
        for value in features.get(feature, ()):
            if value in features:
                pending.append(value)
            elif "/" in value:
                dependency = value.split("/", 1)[0]
                if not dependency.endswith("?") and dependency in features:
                    pending.append(dependency)
    return enabled


def _cargo_target_has_harness(target: dict, manifest_path: Path) -> bool:
    try:
        import tomllib
    except ImportError:  # Python 3.10
        import tomli as tomllib

    try:
        config = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return False
    kinds = set(target["kind"])
    if kinds & {"lib", "rlib", "dylib", "cdylib", "staticlib", "proc-macro"}:
        return config.get("lib", {}).get("harness", True)
    for kind in kinds & {"bin", "test", "example", "bench"}:
        for declaration in config.get(kind, ()):
            if declaration.get("name") == target["name"]:
                return declaration.get("harness", True)
            if (
                "path" in declaration
                and (manifest_path.parent / declaration["path"]).resolve()
                == Path(target["src_path"]).resolve()
            ):
                return declaration.get("harness", True)
    return True


def _is_inline_rust_test(path: str, project_root: Path) -> bool:
    if Path(path).suffix != ".rs":
        return False
    full = project_root / path
    if not full.is_file():
        return False
    try:
        validator = ValidatorRegistry.with_builtin_validators().get(path)
    except UnsupportedLanguageError:
        return False
    try:
        return bool(
            validator.get_test_function_bodies(full.read_text(encoding="utf-8"), path)
        )
    except (OSError, UnicodeError, ValueError):
        # Include invalid candidate syntax so collection emits its parser
        # diagnostic instead of silently excluding the file from validation.
        return True


def _cargo_test_paths(args: list[str], project_root: Path, cwd: Path) -> list[str]:
    """Prove source-file targets for a bounded Cargo test invocation.

    Unknown or filtered invocations produce no coverage. Command-integrity
    validation then reports E311 with the uncovered behavioral files.
    """
    if any(part in {"--quiet", "-q"} for part in args) and any(
        part in {"--verbose", "-v"} for part in args
    ):
        return []
    selectors: list[tuple[str, str | None]] = []
    packages: list[str] = []
    exclude: list[str] = []
    workspace = False
    manifest: str | None = None
    index = 0
    singleton_options = {
        "--lib",
        "--bins",
        "--tests",
        "--all-targets",
        "--workspace",
        "--manifest-path",
        "--color",
        "--offline",
        "--locked",
        "--frozen",
        "--release",
        "--quiet",
    }
    seen_singletons: set[str] = set()
    while index < len(args):
        part = args[index]
        flag, separator, inline = part.partition("=")
        canonical_flag = "--quiet" if flag == "-q" else flag
        if canonical_flag in singleton_options:
            if canonical_flag in seen_singletons:
                return []
            seen_singletons.add(canonical_flag)
        if part == "--":
            if not _safe_harness_args(args[index + 1 :]):
                return []
            break
        if flag in {"--lib", "--bins", "--tests", "--all-targets"}:
            if separator:
                return []
            selectors.append((flag, None))
        elif flag == "--workspace":
            if separator:
                return []
            workspace = True
        elif flag in {
            "--bin",
            "--test",
            "-p",
            "--package",
            "--exclude",
            "--manifest-path",
            "--color",
        }:
            if separator:
                value = inline
            else:
                index += 1
                if index >= len(args):
                    return []
                value = args[index]
            if not value or value.startswith("-"):
                return []
            if flag in {"--bin", "--test"}:
                selectors.append((flag, value))
            elif flag in {"-p", "--package"}:
                packages.append(value)
            elif flag == "--exclude":
                exclude.append(value)
            elif flag == "--manifest-path":
                manifest = value
            elif value not in {"auto", "always", "never"}:
                return []
        elif part not in {
            "--offline",
            "--locked",
            "--frozen",
            "--release",
            "--quiet",
            "-q",
            "--verbose",
            "-v",
        }:
            # No --no-run, --doc, --config, feature/cfg mutation or positional
            # name filters can prove complete execution of a behavioral file.
            return []
        index += 1
    if exclude and not workspace:
        return []
    root = project_root.resolve()
    working = (root / cwd).resolve()
    candidate = working / manifest if manifest is not None else working / "Cargo.toml"
    if manifest is None:
        while (
            not candidate.is_file() and working != root and working.is_relative_to(root)
        ):
            working = working.parent
            candidate = working / "Cargo.toml"
    try:
        candidate = candidate.resolve()
        candidate.relative_to(root)
    except ValueError:
        return []
    if not candidate.is_file():
        return []
    try:
        result = subprocess.run(
            [
                "cargo",
                "metadata",
                "--offline",
                "--no-deps",
                "--format-version",
                "1",
                "--manifest-path",
                str(candidate),
            ],
            cwd=working,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    members = set(data.get("workspace_members", ()))
    if any(
        not any(
            p["id"] in members and _cargo_package_matches(p, pattern)
            for p in data.get("packages", ())
        )
        for pattern in packages
    ):
        return []
    if workspace:
        selected = members
    elif packages:
        selected = {
            p["id"]
            for p in data.get("packages", ())
            if p["id"] in members
            and any(_cargo_package_matches(p, pattern) for pattern in packages)
        }
        if any(
            not any(
                _cargo_package_matches(p, pattern)
                for p in data.get("packages", ())
                if p["id"] in members
            )
            for pattern in packages
        ):
            return []
    else:
        current = next(
            (
                p
                for p in data.get("packages", ())
                if Path(p["manifest_path"]).resolve() == candidate
            ),
            None,
        )
        workspace_manifest = Path(data["workspace_root"]) / "Cargo.toml"
        selected = (
            set(data.get("workspace_default_members", members))
            if candidate == workspace_manifest.resolve()
            else {current["id"]} if current else set()
        )
    selected_packages = [
        package
        for package in data.get("packages", ())
        if package["id"] in selected
        and not any(_cargo_package_matches(package, pattern) for pattern in exclude)
    ]
    for selector, value in selectors:
        if selector == "--lib" and not any(
            set(target["kind"])
            & {"lib", "rlib", "dylib", "cdylib", "staticlib", "proc-macro"}
            for package in selected_packages
            for target in package.get("targets", ())
        ):
            return []
        if selector in {"--bin", "--test"} and not any(
            selector[2:] in target["kind"]
            and fnmatch.fnmatchcase(target["name"], value or "")
            for package in selected_packages
            for target in package.get("targets", ())
        ):
            return []
    paths: list[str] = []
    for package in selected_packages:
        if not Path(package["manifest_path"]).resolve().is_relative_to(root):
            return []
        targets = package.get("targets", ())
        enabled_features = _default_cargo_features(package)
        for target in targets:
            kinds = set(target["kind"])
            if not set(target.get("required-features", ())).issubset(
                enabled_features
            ) and any(
                selector in {"--bin", "--test"}
                and selector[2:] in kinds
                and fnmatch.fnmatchcase(target["name"], value or "")
                for selector, value in selectors
            ):
                # An explicit unavailable target makes Cargo reject the whole
                # invocation, including otherwise valid selected targets.
                return []
            if (
                (not selectors and not target.get("test", True))
                or not _cargo_target_has_harness(target, Path(package["manifest_path"]))
                or not set(target.get("required-features", ())).issubset(
                    enabled_features
                )
            ):
                continue
            eligible = bool(
                kinds
                & {
                    "lib",
                    "rlib",
                    "dylib",
                    "cdylib",
                    "staticlib",
                    "proc-macro",
                    "bin",
                    "test",
                    "example",
                    "bench",
                }
            )
            if selectors:
                eligible = any(
                    (
                        selector == "--all-targets"
                        and bool(
                            kinds
                            & {
                                "lib",
                                "rlib",
                                "dylib",
                                "cdylib",
                                "staticlib",
                                "proc-macro",
                                "bin",
                                "test",
                                "example",
                                "bench",
                            }
                        )
                    )
                    or (
                        selector == "--lib"
                        and bool(
                            kinds
                            & {
                                "lib",
                                "rlib",
                                "dylib",
                                "cdylib",
                                "staticlib",
                                "proc-macro",
                            }
                        )
                    )
                    or (selector == "--bins" and "bin" in kinds)
                    or (selector == "--tests" and target.get("test", True))
                    or (
                        selector in {"--bin", "--test"}
                        and selector[2:] in kinds
                        and fnmatch.fnmatchcase(target["name"], value or "")
                    )
                    for selector, value in selectors
                )
            if eligible:
                loaded = _rust_module_paths(Path(target["src_path"]), root)
                if loaded is None:
                    return []
                paths.extend(loaded)
    return sorted(set(paths))


def _safe_harness_args(args: list[str]) -> bool:
    index = 0
    seen_options: set[str] = set()
    while index < len(args):
        part = args[index]
        option = part.partition("=")[0]
        if option in seen_options:
            return False
        seen_options.add(option)
        if part in {"--nocapture", "--show-output"}:
            pass
        elif part.startswith("--test-threads="):
            if not part.partition("=")[2].isdigit() or int(part.partition("=")[2]) < 1:
                return False
        elif part == "--test-threads" and index + 1 < len(args):
            index += 1
            if not args[index].isdigit() or int(args[index]) < 1:
                return False
        else:
            return False
        index += 1
    return True


def _rust_module_paths(path: Path, root: Path) -> list[str] | None:
    try:
        validator = ValidatorRegistry.with_builtin_validators().get(path)
    except UnsupportedLanguageError:
        return None
    paths: set[str] = set()
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            relative = current.resolve().relative_to(root).as_posix()
            if relative in paths:
                continue
            source = current.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            return None
        paths.add(relative)
        dependencies = validator.collect_dependencies(source, relative, root)
        if not dependencies.supported or dependencies.errors or dependencies.unresolved:
            return None
        pending.extend(root / module for module in dependencies.modules)
    return sorted(paths)
