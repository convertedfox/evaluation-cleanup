import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import flet as ft
import pytest

from evaluation_cleanup import config
from evaluation_cleanup.deletion import DeletionService
from evaluation_cleanup.models import DeleteStatus
from evaluation_cleanup.safety import UnsafePathError, file_stamp
from evaluation_cleanup.workflow import CleanupWorkflow
from tools import demo
from tools.demo import DOCUMENT_LAYOUT, create_demo_files, create_document_demo


def test_demo_structure_dry_run(tmp_path: Path) -> None:
    root = tmp_path / "Seminare"
    paths = create_demo_files(root)
    original = {path: path.read_bytes() for path in paths}
    workflow = CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv"))
    assert workflow.refresh().years == (2022, 2023, 2024, 2025)
    assert len(workflow.search(2024).candidates) == 6
    report = workflow.confirm(workflow.request_confirmation())
    assert report.count(DeleteStatus.SIMULATED) == 6
    assert all(path.read_bytes() == content for path, content in original.items())


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """Kleines synthetisches Archiv; Tests lesen keine echten Dokumenteninhalte."""
    path = tmp_path / "development" / "documents" / "Evaluationen_löschen.zip"
    path.parent.mkdir(parents=True)
    with ZipFile(path, "w") as target:
        for name, _ in DOCUMENT_LAYOUT:
            target.writestr(name, f"Synthetischer Testinhalt: {name}".encode())
    return path


def test_document_demo_copies_bytes_and_finds_expected_years(archive: Path, tmp_path: Path) -> None:
    root = tmp_path / "demo" / "Seminare"
    original_archive = archive.read_bytes()
    paths = create_document_demo(archive, root)
    assert len(paths) == 5
    with ZipFile(archive) as source:
        for path in paths:
            assert path.read_bytes() == source.read(path.name)
    workflow = CleanupWorkflow(DeletionService(root, tmp_path / "demo" / "actions.csv"))
    assert workflow.refresh().years == (2023, 2024, 2025)
    for cutoff, expected in ((2023, 1), (2024, 4), (2025, 5)):
        result = workflow.search(cutoff)
        assert len(result.candidates) == expected
        assert not result.issues
    original = {path: path.read_bytes() for path in paths}
    report = workflow.confirm(workflow.request_confirmation())
    assert report.count(DeleteStatus.SIMULATED) == 5
    assert archive.read_bytes() == original_archive
    assert all(path.read_bytes() == content for path, content in original.items())


def test_repeated_preparation_preserves_files_and_log(archive: Path, tmp_path: Path) -> None:
    root = tmp_path / "demo" / "Seminare"
    paths = create_document_demo(archive, root)
    before = {path: file_stamp(path.stat()) for path in paths}
    log_path = root.parent / "actions.csv"
    log_path.write_text("Bisherige Testläufe", encoding="utf-8")
    assert create_document_demo(archive, root) == paths
    assert all(file_stamp(path.stat()) == info for path, info in before.items())
    assert log_path.read_text(encoding="utf-8") == "Bisherige Testläufe"


def test_conflicting_file_is_not_overwritten(archive: Path, tmp_path: Path) -> None:
    root = tmp_path / "demo" / "Seminare"
    name, folder = DOCUMENT_LAYOUT[-1]
    conflict = root / folder / name
    conflict.parent.mkdir(parents=True)
    conflict.write_bytes(b"Eigene Anpassung")
    with pytest.raises(ValueError, match="wird nicht ersetzt"):
        create_document_demo(archive, root)
    assert conflict.read_bytes() == b"Eigene Anpassung"
    assert not (root / "2023").exists()  # Konflikte vor dem Anlegen anderer Dateien prüfen.


@pytest.mark.parametrize("problem", ["missing", "duplicate", "traversal"])
def test_unexpected_zip_entries_are_rejected(problem: str, archive: Path, tmp_path: Path) -> None:
    with ZipFile(archive, "w") as target:
        for name, _ in DOCUMENT_LAYOUT[:-1]:
            target.writestr(name, b"test")
        if problem == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                target.writestr(DOCUMENT_LAYOUT[0][0], b"duplicate")
        elif problem == "traversal":
            target.writestr("../outside.pdf", b"unexpected")
    root = tmp_path / "demo" / "Seminare"
    with pytest.raises(ValueError, match="genau die fünf"):
        create_document_demo(archive, root)
    assert not root.exists() and not (tmp_path / "outside.pdf").exists()


def test_symlink_demo_directory_is_rejected(archive: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "Seminare"
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlinks benötigen hier zusätzliche Rechte: {error}")
    with pytest.raises(UnsafePathError):
        create_document_demo(archive, root)
    assert not list(outside.iterdir())


def test_document_demo_launcher_retains_files_and_log(
    archive: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo, "__file__", str(tmp_path / "tools" / "demo.py"))
    page = Mock(spec=ft.Page)

    async def fake_main(page: ft.Page, *, workflow: CleanupWorkflow | None = None) -> None:
        assert workflow is not None
        assert workflow.refresh().years == (2023, 2024, 2025)
        assert len(workflow.search(2024).candidates) == 4
        report = workflow.confirm(workflow.request_confirmation())
        assert report.count(DeleteStatus.SIMULATED) == 4

    def fake_run(callback: Callable[[ft.Page], Awaitable[None]]) -> None:
        async def start() -> None:
            await callback(page)

        asyncio.run(start())

    monkeypatch.setattr(demo, "main", fake_main)
    monkeypatch.setattr(ft, "run", fake_run)
    demo.cli(["--documents"])
    base = tmp_path / "development" / "demo"
    assert page.title == "Evaluationen bereinigen – Dokumenten-Demo"
    assert (base / "actions.csv").is_file()
    with ZipFile(archive) as source:
        for name, folder in DOCUMENT_LAYOUT:
            assert (base / "Seminare" / folder / name).read_bytes() == source.read(name)


def test_prepare_only_does_not_launch_gui(
    archive: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo, "__file__", str(tmp_path / "tools" / "demo.py"))
    launcher = Mock(side_effect=AssertionError("Keine GUI beim reinen Einrichten"))
    monkeypatch.setattr(ft, "run", launcher)
    demo.cli(["--documents", "--prepare-only"])
    assert (tmp_path / "development" / "demo" / "Seminare").is_dir()
    launcher.assert_not_called()


def test_document_demo_rejects_enabled_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo, "__file__", str(tmp_path / "tools" / "demo.py"))
    monkeypatch.setattr(config, "DELETE_ENABLED", True)
    with pytest.raises(RuntimeError, match="DELETE_ENABLED = False"):
        demo.run_demo(documents=True)
    assert not (tmp_path / "development").exists()


def test_prepare_only_requires_document_mode() -> None:
    with pytest.raises(SystemExit) as error:
        demo.cli(["--prepare-only"])
    assert error.value.code == 2
