from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from evaluation_cleanup import config
from evaluation_cleanup.deletion import DeletionService
from evaluation_cleanup.models import DeleteStatus
from evaluation_cleanup.workflow import CleanupWorkflow


def test_complete_dry_run_workflow(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    paths = [make_file(f"2024/Kategorie/Seminar/Feedback_{i}.pdf") for i in range(3)]
    newer = make_file("2025/Evaluation.xlsx")
    original_bytes = {path: path.read_bytes() for path in [*paths, newer]}
    workflow = CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv"))
    assert workflow.refresh().years == (2024, 2025)
    assert len(workflow.search(2024).candidates) == 3
    assert workflow.selected == set(paths)
    workflow.select_all(False)
    assert not workflow.selected
    with pytest.raises(ValueError):
        workflow.request_confirmation()
    workflow.select_all(True)
    workflow.select(paths[0], False)
    assert len(workflow.selected) == 2
    canceled = workflow.request_confirmation()
    workflow.cancel_confirmation()
    with pytest.raises(ValueError):
        workflow.confirm(canceled)
    request = workflow.request_confirmation()
    report = workflow.confirm(request)
    assert report.dry_run and report.count(DeleteStatus.SIMULATED) == 2
    assert all(path.read_bytes() == content for path, content in original_bytes.items())
    assert workflow.result is None and not workflow.selected
    with pytest.raises(ValueError):
        workflow.confirm(request)


@pytest.mark.parametrize("change", ["search", "selection", "year", "refresh", "mode"])
def test_stale_confirmations_are_rejected(
    change: str,
    root: Path,
    tmp_path: Path,
    make_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = make_file("2024/Feedback.pdf")
    workflow = CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv"))
    workflow.refresh()
    workflow.search(2024)
    request = workflow.request_confirmation()
    if change == "search":
        workflow.search(2024)
    elif change == "selection":
        workflow.select(path, False)
        workflow.select(path, True)
    elif change == "year":
        workflow.invalidate()
    elif change == "refresh":
        workflow.refresh()
    else:
        monkeypatch.setattr(config, "DELETE_ENABLED", True)
    with pytest.raises(ValueError):
        workflow.confirm(request)
    assert path.exists()


def test_forged_confirmation_and_selection_are_rejected(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    make_file("2024/Feedback.pdf")
    workflow = CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv"))
    workflow.refresh()
    workflow.search(2024)
    with pytest.raises(ValueError):
        workflow.select(tmp_path / "outside.pdf", True)
    request = workflow.request_confirmation()
    with pytest.raises(ValueError):
        workflow.confirm(replace(request))


def test_unreachable_root_blocks_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = CleanupWorkflow(DeletionService(tmp_path / "missing", tmp_path / "actions.csv"))
    assert not workflow.refresh().reachable

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("Bei unerreichbarem Root darf keine Suche gestartet werden.")

    monkeypatch.setattr("evaluation_cleanup.workflow.scan", unexpected)
    with pytest.raises(ValueError, match="nicht erreichbar"):
        workflow.search(2024)


def test_failed_rescan_clears_old_selection(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    make_file("2024/Feedback.pdf")
    workflow = CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv"))
    workflow.refresh()
    workflow.search(2024)
    with pytest.raises(ValueError):
        workflow.search(2025)
    assert workflow.result is None and not workflow.selected
