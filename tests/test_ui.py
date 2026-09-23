"""Headless-Integration mit echten Flet-Controls und temporärem Dateisystem."""

import asyncio
import inspect
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import flet as ft
import pytest

from evaluation_cleanup import config
from evaluation_cleanup.deletion import DeletionService
from evaluation_cleanup.ui import CleanupScreen
from evaluation_cleanup.workflow import CleanupWorkflow


async def dispatch(handler: object, event: object) -> None:
    """Führt den tatsächlich am Flet-Control registrierten Async-Handler aus."""
    assert inspect.iscoroutinefunction(handler)
    await handler(event)


def test_ui_full_dry_run_and_confirmation(
    root: Path,
    tmp_path: Path,
    make_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "DELETE_ENABLED", False)
    paths = [make_file(f"2024/Kategorie/Seminar/Feedback_{i}.pdf") for i in range(2)]
    page = Mock(spec=ft.Page)
    screen = CleanupScreen(page, CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv")))

    async def exercise() -> None:
        await screen.initialize()
        assert not screen.year.disabled and screen.search_button.disabled
        screen.year.value = "2024"
        await dispatch(screen.year.on_select, ft.Event("select", screen.year))
        assert not screen.search_button.disabled
        await dispatch(screen.search_button.on_click, ft.Event("click", screen.search_button))
        assert len(screen.results.controls) == 2
        assert screen.selection_count.value == "2 Dateien ausgewählt"
        assert not screen.delete_button.disabled
        checkbox = screen.checkboxes[paths[0]]
        checkbox.value = False
        await dispatch(checkbox.on_change, ft.Event("change", checkbox))
        assert screen.selection_count.value == "1 Dateien ausgewählt"
        await dispatch(screen.none_button.on_click, ft.Event("click", screen.none_button))
        assert screen.delete_button.disabled
        await dispatch(screen.all_button.on_click, ft.Event("click", screen.all_button))
        assert not screen.delete_button.disabled

        await dispatch(screen.delete_button.on_click, ft.Event("click", screen.delete_button))
        dialog = page.show_dialog.call_args.args[0]
        assert isinstance(dialog, ft.AlertDialog) and dialog.modal
        cancel, confirm = dialog.actions
        assert isinstance(cancel, ft.TextButton) and cancel.autofocus
        assert isinstance(confirm, ft.GestureDetector)
        assert isinstance(confirm.content, ft.Container)
        assert isinstance(confirm.content.content, ft.Text)  # Kein Enter-aktivierbarer Button.
        assert screen.search_button.disabled and screen.delete_button.disabled
        await dispatch(cancel.on_click, ft.Event("click", cancel))
        assert all(path.exists() for path in paths)
        assert not screen.dialog_open and not screen.delete_button.disabled
        assert not screen.workflow.service.log_path.exists()

        await dispatch(screen.delete_button.on_click, ft.Event("click", screen.delete_button))
        old_dialog = dialog
        dialog = page.show_dialog.call_args.args[0]
        confirm = dialog.actions[1]
        # Flet kann das Schließereignis des alten Dialogs verzögert zustellen.
        await dispatch(old_dialog.on_dismiss, object())
        assert screen.dialog_open
        await dispatch(confirm.on_tap, object())
        assert all(path.exists() for path in paths)
        assert "2 Löschungen simuliert" in (screen.message.value or "")
        assert not screen.results.controls and screen.delete_button.disabled
        assert screen.workflow.service.log_path.exists()
        # Ein verzögertes zweites Tap-Ereignis darf keinen neuen Auftrag starten.
        log_before = screen.workflow.service.log_path.read_bytes()
        await dispatch(confirm.on_tap, object())
        assert screen.workflow.service.log_path.read_bytes() == log_before

    asyncio.run(exercise())


def test_ui_unreachable_and_year_change_invalidate_results(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    page = Mock(spec=ft.Page)
    missing_screen = CleanupScreen(
        page, CleanupWorkflow(DeletionService(tmp_path / "missing", tmp_path / "actions.csv"))
    )
    asyncio.run(missing_screen.initialize())
    assert missing_screen.search_button.disabled and missing_screen.year.disabled
    assert missing_screen.status.value == "Nicht erreichbar"
    assert missing_screen.issue_button.visible
    make_file("2024/Feedback.pdf")
    make_file("2025/Evaluation.xlsx")
    screen = CleanupScreen(page, CleanupWorkflow(DeletionService(root, tmp_path / "actions.csv")))

    async def exercise() -> None:
        await screen.initialize()
        screen.year.value = "2024"
        await dispatch(screen.search_button.on_click, ft.Event("click", screen.search_button))
        assert len(screen.results.controls) == 1
        screen.year.value = "2025"
        await dispatch(screen.year.on_select, ft.Event("select", screen.year))
        assert not screen.results.controls and screen.delete_button.disabled
        assert screen.workflow.result is None

    asyncio.run(exercise())
