"""Ein Hauptbildschirm; alle Dateisystemoperationen laufen außerhalb des UI-Threads."""

import asyncio
from pathlib import Path

import flet as ft

from evaluation_cleanup import config
from evaluation_cleanup.models import DeleteReport, DeleteStatus, EvaluationCandidate, FileIssue
from evaluation_cleanup.safety import explain_error
from evaluation_cleanup.workflow import CleanupWorkflow, Confirmation


class CleanupScreen:
    """Bindet native Flet-Steuerelemente an den separat getesteten Workflow."""

    def __init__(self, page: ft.Page, workflow: CleanupWorkflow | None = None) -> None:
        self.page = page
        self.workflow = workflow if workflow is not None else CleanupWorkflow()
        self.busy = False
        self.dialog_open = False
        self._dialog_request: Confirmation | None = None
        self.checkboxes: dict[Path, ft.Checkbox] = {}
        self.issues: tuple[FileIssue, ...] = ()
        self.status = ft.Text("Basisordner wird geprüft …")
        self.message = ft.Text("", selectable=True)
        self.progress = ft.ProgressBar(visible=False)
        self.year = ft.Dropdown(
            label="Evaluationen suchen bis einschließlich",
            width=370,
            disabled=True,
            on_select=self._year_changed,
        )
        self.refresh_button = ft.TextButton("Erneut prüfen", on_click=self._refresh_clicked)
        self.search_button = ft.Button("Evaluationen suchen", on_click=self._search, disabled=True)
        self.all_button = ft.TextButton("Alle auswählen", on_click=self._select_all, disabled=True)
        self.none_button = ft.TextButton("Alle abwählen", on_click=self._select_none, disabled=True)
        self.issue_button = ft.TextButton(
            "Hinweise anzeigen", on_click=self._show_issues, visible=False
        )
        self.count = ft.Text("Noch keine Suche durchgeführt.")
        self.selection_count = ft.Text("0 Dateien ausgewählt")
        self.results = ft.ListView(expand=True, spacing=8)
        self.delete_button = ft.Button(
            "Auswahl löschen",
            on_click=self._ask_delete,
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.ERROR_CONTAINER, color=ft.Colors.ON_ERROR_CONTAINER
            ),
        )
        self.control = ft.Column(
            [
                ft.Text("Evaluationen bereinigen", size=26, weight=ft.FontWeight.BOLD),
                ft.Container(
                    ft.Text(
                        "TESTMODUS – Dateien werden nicht gelöscht",
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_TERTIARY_CONTAINER,
                    ),
                    bgcolor=ft.Colors.TERTIARY_CONTAINER,
                    padding=12,
                    visible=not config.DELETE_ENABLED,
                ),
                ft.Text("Basisordner", weight=ft.FontWeight.BOLD),
                ft.Text(str(self.workflow.service.root), selectable=True),
                ft.Row([self.status, self.refresh_button], wrap=True),
                ft.Row([self.year, self.search_button], wrap=True),
                self.progress,
                self.message,
                ft.Divider(),
                ft.Row([self.count, self.issue_button], wrap=True),
                ft.Row([self.all_button, self.none_button]),
                self.results,
                ft.Divider(),
                ft.Row([self.selection_count, self.delete_button], wrap=True),
            ],
            expand=True,
            spacing=10,
        )

    async def initialize(self) -> None:
        """Prüft den Root nach Anzeige des Fensters im Hintergrund."""
        await self._refresh()

    def _sync(self) -> None:
        locked = self.busy or self.dialog_open
        available = self.workflow.status.reachable and bool(self.workflow.status.years)
        self.year.disabled = locked or not available
        self.refresh_button.disabled = locked
        self.search_button.disabled = locked or not available or self.year.value is None
        has_results = bool(self.workflow.result and self.workflow.result.candidates)
        self.all_button.disabled = self.none_button.disabled = locked or not has_results
        self.delete_button.disabled = locked or not self.workflow.selected
        self.results.disabled = locked
        self.issue_button.disabled = locked
        self.progress.visible = self.busy
        self.selection_count.value = f"{len(self.workflow.selected)} Dateien ausgewählt"
        for path, checkbox in self.checkboxes.items():
            checkbox.value = path in self.workflow.selected
        self.page.update()

    def _clear_results(self) -> None:
        self.results.controls.clear()
        self.checkboxes.clear()
        self.issues = ()
        self.issue_button.visible = False
        self.count.value = "Noch keine Suche durchgeführt."

    async def _refresh_clicked(self, event: ft.Event[ft.TextButton]) -> None:
        await self._refresh()

    async def _refresh(self) -> None:
        if self.busy or self.dialog_open:
            return
        self.busy = True
        self._clear_results()
        self.message.value = "Basisordner wird geprüft …"
        self._sync()
        try:
            status = await asyncio.to_thread(self.workflow.refresh)
            self.year.options = [ft.DropdownOption(key=f"{year:04d}") for year in status.years]
            self.year.value = None
            self.issues = status.issues
            self.issue_button.visible = bool(self.issues)
            if not status.reachable:
                self.status.value = "Nicht erreichbar"
                self.message.value = "Bitte prüfen Sie, ob das Laufwerk T: verbunden ist."
            elif not status.years:
                self.status.value = "Laufwerk erreichbar"
                self.message.value = "Keine vierstelligen Jahresordner gefunden."
            else:
                self.status.value = "Laufwerk erreichbar"
                self.message.value = "Bitte das gewünschte Grenzjahr auswählen."
        finally:
            self.busy = False
            self._sync()

    async def _year_changed(self, event: ft.Event[ft.Dropdown]) -> None:
        if self.busy or self.dialog_open:
            return
        self.workflow.invalidate()
        self._clear_results()
        self.message.value = "Bitte die Suche für den gewählten Zeitraum starten."
        self._sync()

    async def _search(self, event: ft.Event[ft.Button]) -> None:
        if self.busy or self.dialog_open or self.year.value is None:
            return
        self.busy = True
        self.workflow.invalidate()
        self._clear_results()
        self.message.value = "Dateien werden gesucht. Dies kann auf dem Netzlaufwerk etwas dauern …"
        self._sync()
        try:
            result = await asyncio.to_thread(self.workflow.search, int(self.year.value))
            self.results.controls = [self._candidate_row(item) for item in result.candidates]
            self.issues = result.issues
            self.issue_button.visible = bool(self.issues)
            self.count.value = f"{len(result.candidates)} mögliche Evaluationen gefunden"
            self.message.value = (
                f"Suche abgeschlossen. {len(self.issues)} Pfade wurden übersprungen; "
                "bitte Hinweise prüfen."
                if self.issues
                else "Bitte die Treffer prüfen und unerwünschte Häkchen entfernen."
            )
        except (OSError, ValueError) as error:
            self.workflow.invalidate()
            self.message.value = explain_error(error)
        finally:
            self.busy = False
            self._sync()

    def _candidate_row(self, item: EvaluationCandidate) -> ft.Control:
        async def changed(event: ft.Event[ft.Checkbox]) -> None:
            if not self.busy and not self.dialog_open:
                self.workflow.select(item.path, event.control.value is True)
                self._sync()

        checkbox = ft.Checkbox(value=True, on_change=changed, tooltip=f"{item.filename} auswählen")
        self.checkboxes[item.path] = checkbox
        relative = str(item.path.relative_to(self.workflow.service.root))
        return ft.Container(
            ft.Row(
                [
                    checkbox,
                    ft.Text(f"{item.year:04d}", width=48),
                    ft.Column(
                        [
                            ft.Text(
                                item.filename,
                                weight=ft.FontWeight.BOLD,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                tooltip=item.filename,
                            ),
                            ft.Text(
                                f"{item.category or 'Ohne Kategorie'} · "
                                f"{item.seminar or 'Ohne Seminar'}",
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                tooltip=f"{item.category}\n{item.seminar}",
                            ),
                            ft.Text(
                                relative,
                                size=12,
                                selectable=True,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                tooltip=str(item.path),
                            ),
                        ],
                        expand=True,
                        spacing=3,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=10,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        )

    async def _select_all(self, event: ft.Event[ft.TextButton]) -> None:
        if not self.busy and not self.dialog_open:
            self.workflow.select_all(True)
            self._sync()

    async def _select_none(self, event: ft.Event[ft.TextButton]) -> None:
        if not self.busy and not self.dialog_open:
            self.workflow.select_all(False)
            self._sync()

    async def _show_issues(self, event: ft.Event[ft.TextButton]) -> None:
        self._show_details(
            "Übersprungene Pfade",
            [f"{issue.path}\n{issue.message}" for issue in self.issues],
        )

    def _show_details(self, title: str, lines: list[str]) -> None:
        async def close(event: ft.Event[ft.TextButton]) -> None:
            self.page.pop_dialog()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Container(
                    ft.ListView([ft.Text(line, selectable=True) for line in lines], spacing=16),
                    width=680,
                    height=330,
                ),
                actions=[ft.TextButton("Schließen", on_click=close, autofocus=True)],
            )
        )

    async def _ask_delete(self, event: ft.Event[ft.Button]) -> None:
        if self.busy or self.dialog_open or not self.workflow.selected:
            return
        request = self.workflow.request_confirmation()
        self._dialog_request = request
        self.dialog_open = True
        self._sync()

        async def cancel(event: ft.Event[ft.TextButton]) -> None:
            if self._dialog_request is not request:
                return
            self._dialog_request = None
            self.workflow.cancel_confirmation()
            self.dialog_open = False
            self.page.pop_dialog()
            self._sync()

        async def dismissed(event: object) -> None:
            if self._dialog_request is request:
                self._dialog_request = None
                self.workflow.cancel_confirmation()
                self.dialog_open = False
                self._sync()

        async def confirm(event: ft.TapEvent[ft.GestureDetector]) -> None:
            await self._confirm(request)

        count = len(request.paths)
        label = (
            f"{count} Dateien löschen"
            if request.delete_enabled
            else f"{count} Dateien testweise löschen"
        )
        # GestureDetector hat keinen Tastaturfokus und keine Enter-Standardaktion.
        # Kein nativer Button darin: dieser würde Enter erneut aktivieren können.
        confirm_action = ft.GestureDetector(
            on_tap=confirm,
            mouse_cursor=ft.MouseCursor.CLICK,
            content=ft.Container(
                ft.Text(label, color=ft.Colors.ON_ERROR, weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.ERROR,
                padding=14,
                border_radius=6,
            ),
        )
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    f"{count} Dateien wirklich löschen?"
                    if request.delete_enabled
                    else "Testlauf bestätigen"
                ),
                content=ft.Column(
                    [
                        ft.Text(
                            "Die ausgewählten Dateien werden endgültig gelöscht, "
                            "nicht in den Papierkorb verschoben."
                            if request.delete_enabled
                            else "TESTMODUS – Dateien werden nicht gelöscht."
                        ),
                        ft.Text(
                            f"Erlaubter Bereich:\n{self.workflow.service.root}", selectable=True
                        ),
                        ft.Text(
                            "Zum Bestätigen die beschriftete Fläche mit Maus oder Touch anklicken."
                        ),
                    ],
                    tight=True,
                    width=550,
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=cancel, autofocus=True),
                    confirm_action,
                ],
                on_dismiss=dismissed,
            )
        )

    async def _confirm(self, request: Confirmation) -> None:
        if self.busy or not self.dialog_open or self._dialog_request is not request:
            return
        self._dialog_request = None
        self.busy = True
        self.dialog_open = False
        self.page.pop_dialog()
        self.message.value = "Auswahl wird geprüft und verarbeitet …"
        self._sync()
        try:
            report = await asyncio.to_thread(self.workflow.confirm, request)
            self._clear_results()
            self.message.value = (
                self._report_summary(report) + " Für weitere Aktionen bitte erneut suchen."
            )
            lines = [self._report_summary(report), f"Protokoll: {report.log_path}"]
            if report.log_error:
                lines.append(report.log_error)
            lines.extend(
                f"{item.path}\n{item.message}"
                for item in report.outcomes
                if item.status in (DeleteStatus.ERROR, DeleteStatus.MISSING)
            )
            self._show_details("Ergebnis", lines)
        except (OSError, ValueError) as error:
            self.workflow.invalidate()
            self._clear_results()
            self.message.value = explain_error(error)
        finally:
            self.busy = False
            self._sync()

    @staticmethod
    def _report_summary(report: DeleteReport) -> str:
        success = (
            f"{report.count(DeleteStatus.SIMULATED)} Löschungen simuliert – keine Dateien gelöscht"
            if report.dry_run
            else f"{report.count(DeleteStatus.DELETED)} Dateien gelöscht"
        )
        return (
            f"{success}; {report.count(DeleteStatus.MISSING)} Dateien nicht mehr vorhanden; "
            f"{report.count(DeleteStatus.ERROR)} Dateien konnten nicht verarbeitet werden."
        )
