"""GUI-unabhängiger Ablauf: aktueller Scan, Auswahl und einmalige Bestätigung."""

from dataclasses import dataclass
from pathlib import Path

from evaluation_cleanup import config
from evaluation_cleanup.deletion import DeletionService
from evaluation_cleanup.models import DeleteReport, RootStatus, ScanResult
from evaluation_cleanup.scanner import inspect_root, scan


@dataclass(frozen=True)
class Confirmation:
    scan: ScanResult
    paths: tuple[Path, ...]
    delete_enabled: bool


class CleanupWorkflow:
    """Hält Zustand pro Fenster; keine GUI-Abhängigkeit oder globale Auswahl."""

    def __init__(self, service: DeletionService | None = None) -> None:
        self.service = service if service is not None else DeletionService()
        self.status = RootStatus(False)
        self.result: ScanResult | None = None
        self._selected: set[Path] = set()
        self._pending: Confirmation | None = None

    @property
    def selected(self) -> frozenset[Path]:
        """Schreibgeschützte aktuelle Auswahl."""
        return frozenset(self._selected)

    def invalidate(self) -> None:
        """Verwirft Scan, Auswahl und Bestätigung, etwa beim Wechsel des Grenzjahres."""
        self.result = None
        self._selected.clear()
        self.cancel_confirmation()

    def refresh(self) -> RootStatus:
        """Prüft den Basisordner neu und verwirft vorherige Scanergebnisse."""
        self.invalidate()
        self.status = inspect_root(self.service.root)
        return self.status

    def search(self, cutoff: int) -> ScanResult:
        """Sucht nur nach erfolgreicher Root-Prüfung und wählt die Treffer vor."""
        self.invalidate()
        if not self.status.reachable:
            raise ValueError("Der Basisordner ist nicht erreichbar. Bitte zuerst erneut prüfen.")
        if cutoff not in self.status.years:
            raise ValueError("Bitte ein verfügbares Jahr auswählen.")
        self.result = scan(cutoff, self.service.root)
        self._selected = {item.path for item in self.result.candidates}
        return self.result

    def select(self, path: Path, selected: bool) -> None:
        """Ändert ausschließlich die Auswahl eines Mitglieds des aktuellen Scans."""
        if self.result is None or path not in {item.path for item in self.result.candidates}:
            raise ValueError("Diese Datei gehört nicht zum aktuellen Scan.")
        self.cancel_confirmation()
        if selected:
            self._selected.add(path)
        else:
            self._selected.discard(path)

    def select_all(self, selected: bool) -> None:
        """Wählt alle aktuellen Kandidaten oder keinen davon aus."""
        self.cancel_confirmation()
        self._selected = (
            {item.path for item in self.result.candidates} if selected and self.result else set()
        )

    def request_confirmation(self) -> Confirmation:
        """Friert die aktuelle Auswahl für genau einen Bestätigungsdialog ein."""
        if self.result is None or not self.result.completed or not self._selected:
            raise ValueError("Bitte zuerst suchen und mindestens eine Datei auswählen.")
        paths = tuple(item.path for item in self.result.candidates if item.path in self._selected)
        self._pending = Confirmation(self.result, paths, config.DELETE_ENABLED)
        return self._pending

    def cancel_confirmation(self) -> None:
        """Verwirft eine offene Bestätigung ohne Dateisystemoperation."""
        self._pending = None

    def confirm(self, request: Confirmation) -> DeleteReport:
        """Verbraucht die Bestätigung vor dem Auftrag, auch bei Fehlern und Doppelklicks."""
        if (
            request is not self._pending
            or request.scan is not self.result
            or frozenset(request.paths) != self.selected
            or request.delete_enabled != config.DELETE_ENABLED
        ):
            raise ValueError("Die Bestätigung ist nicht mehr aktuell. Bitte erneut suchen.")
        self.invalidate()
        return self.service.execute(request.scan, request.paths, confirmed=True)
