import csv
import os
import stat
import subprocess
from collections.abc import Callable
from dataclasses import replace
from os import stat_result
from pathlib import Path
from types import SimpleNamespace
from typing import TextIO

import pytest

from evaluation_cleanup import config, deletion
from evaluation_cleanup.deletion import DeletionService
from evaluation_cleanup.models import DeleteOutcome, DeleteStatus
from evaluation_cleanup.safety import RootGuard, UnsafePathError, checked_stat
from evaluation_cleanup.scanner import scan


def test_guard_accepts_only_regular_files(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    path = make_file("2024/Feedback.pdf")
    guard = RootGuard(root)
    assert guard.file(path)
    for invalid in (root, path.parent, tmp_path / "outside.pdf", root / "2024" / ".." / "x"):
        with pytest.raises(UnsafePathError):
            guard.file(invalid)
    with pytest.raises(FileNotFoundError):
        guard.file(root / "missing.pdf")


@pytest.mark.parametrize("enabled", [False, True])
def test_switch_and_logging(
    enabled: bool,
    root: Path,
    tmp_path: Path,
    make_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = make_file("2024/Kategorie/Seminar/Feedback.pdf")
    result = scan(2024, root)
    monkeypatch.setattr(config, "DELETE_ENABLED", enabled)
    log_path = tmp_path / "logs" / "actions.csv"
    report = DeletionService(root, log_path).execute(result, [path, path], confirmed=True)
    assert len(report.outcomes) == 1  # Doppelte Auswahl löscht nie zweimal.
    assert report.count(DeleteStatus.DELETED if enabled else DeleteStatus.SIMULATED) == 1
    assert path.exists() is not enabled
    assert path.parent.is_dir()
    with log_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream, delimiter=";"))
    assert len(rows) == 2 and len(rows[0]) == 6
    assert rows[0][4] == "START"
    assert rows[1][1] == ("DELETE" if enabled else "DRY_RUN")
    assert rows[1][2] == str(path)
    assert rows[1][3] == "2024"
    assert "Dummy evaluation" not in log_path.read_text()


def test_requires_scan_selection_confirmation(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    path = make_file("2024/Feedback.pdf")
    result = scan(2024, root)
    service = DeletionService(root, tmp_path / "actions.csv")
    for scan_result, paths, confirmed in (
        (result, [path], False),
        (result, [], True),
        (replace(result, completed=False), [path], True),
    ):
        with pytest.raises(ValueError):
            service.execute(scan_result, paths, confirmed=confirmed)
    assert path.exists() and not service.log_path.exists()


def test_outside_and_unscanned_files_cannot_be_deleted(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    safe = make_file("2024/Feedback.pdf")
    outside = tmp_path / "outside" / "wichtige_datei.pdf"
    outside.parent.mkdir()
    outside.write_text("important")
    result = scan(2024, root)
    unseen = make_file("2024/Evaluation_neu.pdf")
    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    service = DeletionService(root, tmp_path / "actions.csv")
    report = service.execute(result, [outside, unseen], confirmed=True)
    assert report.count(DeleteStatus.ERROR) == 2
    # Selbst manipulierte Kandidaten überwinden die Root-Prüfung nicht.
    forged = replace(result.candidates[0], path=outside)
    report = service.execute(replace(result, candidates=(forged,)), [outside], confirmed=True)
    assert report.count(DeleteStatus.ERROR) == 1
    assert safe.exists() and outside.exists() and unseen.exists()


def test_missing_changed_directory_and_individual_errors(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = make_file("2024/Feedback_missing.pdf")
    changed = make_file("2024/Feedback_changed.pdf")
    directory = make_file("2024/Feedback_directory.pdf")
    blocked = make_file("2024/Feedback_blocked.pdf")
    good = make_file("2024/Feedback_good.pdf")
    result = scan(2024, root)
    missing.unlink()
    changed.write_text("Changed after scan")
    directory.unlink()
    directory.mkdir()
    original = Path.unlink

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path == blocked:
            raise PermissionError("Test: file open")
        original(path, missing_ok=missing_ok)

    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    monkeypatch.setattr(Path, "unlink", unlink)
    report = DeletionService(root, tmp_path / "actions.csv").execute(
        result, [missing, changed, directory, blocked, good], confirmed=True
    )
    assert report.count(DeleteStatus.MISSING) == 1
    assert report.count(DeleteStatus.ERROR) == 3
    assert report.count(DeleteStatus.DELETED) == 1
    assert changed.exists() and directory.is_dir() and blocked.exists() and not good.exists()


def test_parent_replaced_with_symlink_is_rejected(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = make_file("2024/Seminar/Feedback.pdf")
    result = scan(2024, root)
    outside = tmp_path / "outside"
    outside.mkdir()
    important = outside / path.name
    important.write_text("important")
    path.parent.rename(root / "2024" / "Original")
    try:
        path.parent.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlinks benötigen hier zusätzliche Rechte: {error}")
    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    report = DeletionService(root, tmp_path / "actions.csv").execute(result, [path], confirmed=True)
    assert report.count(DeleteStatus.ERROR) == 1
    assert important.read_text() == "important"


def test_reparse_attributes_are_rejected(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.lstat

    def lstat(path: Path) -> stat_result | SimpleNamespace:
        if path == root:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
            )
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(UnsafePathError, match="Junctions"):
        checked_stat(root)


def test_log_failure_prevents_deletion(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = make_file("2024/Feedback.pdf")
    result = scan(2024, root)
    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    report = DeletionService(root, tmp_path).execute(result, [path], confirmed=True)
    assert report.log_error and report.count(DeleteStatus.ERROR) == 1
    assert path.exists()


def test_log_write_failure_stops_batch(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [make_file(f"2024/Feedback_{index}.pdf") for index in range(2)]
    result = scan(2024, root)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("Disk full")

    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    monkeypatch.setattr(deletion, "_write_log", fail)
    report = DeletionService(root, tmp_path / "actions.csv").execute(result, paths, confirmed=True)
    assert report.log_error and report.count(DeleteStatus.ERROR) == 2
    assert all(path.exists() for path in paths)


def test_root_identity_change_is_rejected(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = make_file("2024/Feedback.pdf")
    result = scan(2024, root)
    root.rename(tmp_path / "old_root")
    new_path = make_file("2024/Feedback.pdf")
    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    report = DeletionService(root, tmp_path / "actions.csv").execute(result, [path], confirmed=True)
    assert report.count(DeleteStatus.ERROR) == 1 and new_path.exists()


def test_hardlinks_are_rejected(root: Path, make_file: Callable[[str], Path]) -> None:
    path = make_file("2024/Feedback.pdf")
    (root / "alias.pdf").hardlink_to(path)
    with pytest.raises(UnsafePathError, match="Hardlinks"):
        RootGuard(root).file(path)


def test_result_log_failure_preserves_truth_and_stops_remaining_files(
    root: Path,
    tmp_path: Path,
    make_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [make_file(f"2024/Feedback_{index}.pdf") for index in range(2)]
    result = scan(2024, root)
    original = deletion._write_log

    def write_log(stream: TextIO, action: str, outcome: DeleteOutcome, result: str = "") -> None:
        if result != "START":
            raise OSError("Disk full after deletion")
        original(stream, action, outcome, result)

    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    monkeypatch.setattr(deletion, "_write_log", write_log)
    report = DeletionService(root, tmp_path / "actions.csv").execute(result, paths, confirmed=True)
    assert report.log_error
    assert report.count(DeleteStatus.DELETED) == report.count(DeleteStatus.ERROR) == 1
    assert not paths[0].exists() and paths[1].exists()


@pytest.mark.skipif(os.name != "nt", reason="Echte Windows-Junction erfordert Windows")
def test_windows_junction_replacement_is_rejected(
    root: Path,
    tmp_path: Path,
    make_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = make_file("2024/Seminar/Feedback.pdf")
    result = scan(2024, root)
    outside = tmp_path / "outside"
    outside.mkdir()
    important = outside / path.name
    important.write_text("important")
    path.parent.rename(root / "2024" / "Original")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(path.parent), str(outside)],
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    report = DeletionService(root, tmp_path / "actions.csv").execute(result, [path], confirmed=True)
    assert report.count(DeleteStatus.ERROR) == 1
    assert important.read_text() == "important"
