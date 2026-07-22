"""C# behavioral test filename discovery regressions."""

from maid_runner.core._file_discovery import is_test_file


def test_is_test_file_recognizes_csharp_tests_suffix():
    assert is_test_file("InductionWorkflowServiceTests.cs") is True
    assert is_test_file("VolunteerDesk.Tests/Services/WorkflowTests.cs") is True


def test_is_test_file_rejects_csharp_near_misses():
    assert is_test_file("Workflow.cs") is False
    assert is_test_file("WorkflowTest.cs") is False
    assert is_test_file("tests.cs") is False
    assert is_test_file("WorkflowTests.CS") is False
