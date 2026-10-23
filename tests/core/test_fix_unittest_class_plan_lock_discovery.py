"""Unittest and Django behavioral inputs stay protected by plan locks."""

from pathlib import Path

import pytest
import yaml

from maid_runner.core._command_integrity_test_discovery import (
    find_command_integrity_test_files,
    is_python_behavioral_test_file,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.plan_lock import (
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


def _project(
    tmp_path: Path,
    source: str,
    *,
    scope: bool = False,
    command: list[str] | None = None,
) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_policy.py").write_text(source)
    (tmp_path / "manifests").mkdir()
    files = (
        {"scope": [{"path": "tests/test_policy.py", "reason": "Behavioral regression"}]}
        if scope
        else {"read": ["tests/test_policy.py"]}
    )
    (tmp_path / "service.py").write_text("VALUE = 1\n")
    files.setdefault("scope", []).append(
        {"path": "service.py", "reason": "Production boundary"}
    )
    path = tmp_path / "manifests/policy.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Protect policy tests",
                "type": "fix",
                "created": "2026-10-20",
                "files": files,
                "validate": [
                    command or ["python", "-m", "unittest", "tests/test_policy.py"]
                ],
            }
        )
    )
    return path


@pytest.mark.parametrize(
    "source",
    [
        "import unittest\nclass PolicyTests(unittest.TestCase):\n    def test_policy(self): assert False\n",
        "import unittest as ut\nclass PolicyTests(ut.TestCase):\n    def test_policy(self): assert False\n",
        "from unittest import TestCase as Case\nclass PolicyTests(Case):\n    def test_policy(self): assert False\n",
        "from django.test import TestCase\nclass PolicyTests(TestCase):\n    def test_policy(self): assert False\n",
        "from django import test as dt\nclass PolicyTests(dt.TransactionTestCase):\n    def test_policy(self): assert False\n",
        "from django.test import SimpleTestCase\nclass PolicyTests(SimpleTestCase):\n    def test_policy(self): assert False\n",
        "from unittest import TestCase\nclass Base(TestCase): pass\nclass PolicyTests(Base):\n    def test_policy(self): assert False\n",
        "from django.test.testcases import TestCase as Case\nclass PolicyTests(Case):\n    def test_policy(self): assert False\n",
        "from unittest import IsolatedAsyncioTestCase as Case\nclass PolicyTests(Case):\n    async def test_policy(self): assert False\n",
        "from unittest.async_case import IsolatedAsyncioTestCase\nclass PolicyTests(IsolatedAsyncioTestCase):\n    async def test_policy(self): assert False\n",
        "import unittest\nclass PolicyTests(unittest.TestCase):\n    def testPolicy(self): assert False\n",
        "from django.test import TestCase\nclass PolicyTests(TestCase):\n    def testPolicy(self): assert False\n",
        "import unittest\nclass PolicyTests(unittest.TestCase):\n    def runTest(self): assert False\n",
        "from django.test import TestCase\nclass PolicyTests(TestCase):\n    def runTest(self): assert False\n",
        "from django.contrib.staticfiles.testing import StaticLiveServerTestCase as Case\nclass PolicyTests(Case):\n    def test_policy(self): assert False\n",
        "class TestPolicy:\n    def test_policy(self): assert False\n",
    ],
)
def test_unittest_suffix_class_is_hashed(tmp_path: Path, source: str) -> None:
    path = _project(tmp_path, source)
    assert is_python_behavioral_test_file("tests/test_policy.py", tmp_path)
    assert find_command_integrity_test_files(load_manifest(path), tmp_path) == [
        "tests/test_policy.py"
    ]
    assert set(create_plan_lock(path, tmp_path).test_hashes) == {"tests/test_policy.py"}


def test_scope_only_test_file_is_hashed(tmp_path: Path) -> None:
    path = _project(
        tmp_path,
        "def test_policy(): assert False\n",
        scope=True,
        command=["python", "-m", "pytest", "unrelated"],
    )
    assert find_command_integrity_test_files(load_manifest(path), tmp_path) == []
    assert find_command_integrity_test_files(
        load_manifest(path), tmp_path, include_scope=True
    ) == ["tests/test_policy.py"]
    lock = create_plan_lock(path, tmp_path)
    assert set(lock.test_hashes) == {"tests/test_policy.py"}
    lock.save(default_plan_lock_path(tmp_path, "policy"))
    for replacement in (
        "def test_policy(): assert True\n",
        "def helper(): pass\n",
        None,
    ):
        test_file = tmp_path / "tests/test_policy.py"
        if replacement is None:
            test_file.unlink()
        else:
            test_file.write_text(replacement)
        errors = enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=False,
        )
        assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
            error.code for error in errors
        }


@pytest.mark.parametrize(
    "source",
    [
        "class PolicyTests:\n    def test_policy(self): pass\n",
        "from unrelated import TestCase\nclass PolicyTests(TestCase):\n    def test_policy(self): pass\n",
        "import unrelated as unittest\nclass PolicyTests(unittest.TestCase):\n    def test_policy(self): pass\n",
        "from unittest import TestCase\nclass PolicyTests(TestCase):\n    def helper(self): pass\n",
    ],
)
def test_unrelated_class_does_not_become_test(tmp_path: Path, source: str) -> None:
    path = _project(tmp_path, source, scope=True)
    assert not is_python_behavioral_test_file("tests/test_policy.py", tmp_path)
    assert find_command_integrity_test_files(load_manifest(path), tmp_path) == []
    assert create_plan_lock(path, tmp_path).test_hashes == {}


@pytest.mark.parametrize(
    "command",
    [
        ["python", "-m", "unittest", "tests/test_policy.py"],
        ["python", "manage.py", "test", "tests.test_policy"],
    ],
)
def test_changed_unittest_test_fails_lock(tmp_path: Path, command: list[str]) -> None:
    path = _project(
        tmp_path,
        "from unittest import TestCase\nclass PolicyTests(TestCase):\n    def test_policy(self): assert False\n",
        command=command,
    )
    lock = create_plan_lock(path, tmp_path)
    lock.save(default_plan_lock_path(tmp_path, "policy"))
    (tmp_path / "tests/test_policy.py").write_text(
        "from unittest import TestCase\nclass PolicyTests(TestCase):\n    def test_policy(self): assert True\n"
    )
    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }
