"""Einzeldatei-Löschung mit Scanabgleich, Sicherheitsprüfung und lokalem CSV-Protokoll."""

import csv
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import TextIO

from evaluation_cleanup import config
from evaluation_cleanup.models import (
    DeleteOutcome,
    DeleteReport,
    DeleteStatus,
    EvaluationCandidate,
    ScanResult,
)
from evaluation_cleanup.safety import RootGuard, UnsafePathError, explain_error


def default_log_path() -> Path:
    """Lokales App-Daten-Verzeichnis; niemals ein Seminarordner."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return base / "evaluation-cleanup" / "actions.csv"


def _write_log(stream: TextIO, action: str, outcome: DeleteOutcome, result: str = "") -> None:
    csv.writer(stream, delimiter=";").writerow(
        (
            datetime.now().astimezone().isoformat(timespec="seconds"),
            action,
            str(outcome.path),
            outcome.year if outcome.year is not None else "",
            result or outcome.status.value,
            outcome.message,
        )
    )
    stream.flush()
    os.fsync(stream.fileno())


class DeletionService:
    """Löscht nur bestätigte Scanmitglieder; der Produktionsschalter liegt in config.

    Root und Logpfad sind für isolierte Tests injizierbar. Die GUI verwendet
    ausschließlich die festen Produktionswerte, keine Benutzereingabe.
    """

    def __init__(self, root: Path = config.ALLOWED_ROOT, log_path: Path | None = None) -> None:
        self.root = root
        self.log_path = log_path if log_path is not None else default_log_path()

    def execute(
        self, scan: ScanResult, selected: Iterable[Path], *, confirmed: bool
    ) -> DeleteReport:
        """Prüft jeden Pfad erneut und liefert auch bei einzelnen Fehlern alle Ergebnisse.

        Ohne bestätigten, abgeschlossenen Scan wird der gesamte Auftrag abgewiesen.
        Bei Protokollfehlern werden keine weiteren Dateien gelöscht.
        """
        paths = tuple(dict.fromkeys(selected))
        if confirmed is not True or not scan.completed or not paths:
            raise ValueError(
                "Zum Löschen sind ein abgeschlossener Scan, Auswahl und Bestätigung nötig."
            )
        dry_run = not config.DELETE_ENABLED
        action = "DRY_RUN" if dry_run else "DELETE"
        candidates = {item.path: item for item in scan.candidates}
        outcomes: list[DeleteOutcome] = []
        log_error = ""
        try:
            guard = RootGuard(self.root)
            if scan.root != guard.root or scan.root_identity != guard.identity:
                raise UnsafePathError("Der Scan gehört nicht zum aktuellen Basisordner.")
            if self.log_path.resolve().is_relative_to(guard.root):
                raise UnsafePathError("Das Protokoll muss außerhalb der Seminarordner liegen.")
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            stream = self.log_path.open("a", encoding="utf-8", newline="")
        except (OSError, ValueError) as error:
            message = f"Auftrag nicht ausgeführt: {explain_error(error)}"
            return DeleteReport(
                tuple(
                    DeleteOutcome(
                        path,
                        candidates[path].year if path in candidates else None,
                        DeleteStatus.ERROR,
                        message,
                    )
                    for path in paths
                ),
                dry_run,
                self.log_path,
                message,
            )
        try:
            for path in paths:
                candidate = candidates.get(path)
                year = candidate.year if candidate else None
                if log_error:
                    outcomes.append(DeleteOutcome(path, year, DeleteStatus.ERROR, log_error))
                    continue
                try:
                    # Erst protokollieren; danach direkt vor unlink erneut validieren.
                    _write_log(
                        stream, action, DeleteOutcome(path, year, DeleteStatus.ERROR), "START"
                    )
                except OSError as error:
                    log_error = (
                        f"Protokoll nicht schreibbar; Vorgang gestoppt: {explain_error(error)}"
                    )
                    outcomes.append(DeleteOutcome(path, year, DeleteStatus.ERROR, log_error))
                    continue
                outcome = self._process(guard, scan, path, candidate, dry_run)
                outcomes.append(outcome)
                try:
                    _write_log(stream, action, outcome)
                except OSError as error:
                    log_error = f"Ergebnisprotokoll fehlgeschlagen: {explain_error(error)}"
        finally:
            try:
                stream.close()
            except OSError as error:
                log_error = f"Protokoll konnte nicht geschlossen werden: {explain_error(error)}"
        return DeleteReport(tuple(outcomes), dry_run, self.log_path, log_error)

    @staticmethod
    def _process(
        guard: RootGuard,
        scan: ScanResult,
        path: Path,
        candidate: EvaluationCandidate | None,
        dry_run: bool,
    ) -> DeleteOutcome:
        year = candidate.year if candidate else None
        try:
            if candidate is None:
                raise UnsafePathError("Die Datei ist nicht Teil des aktuellen Scanergebnisses.")
            if candidate.year > scan.cutoff:
                raise UnsafePathError("Die Datei liegt außerhalb des ausgewählten Zeitraums.")
            if guard.file(path) != candidate.stamp:
                raise UnsafePathError(
                    "Die Datei wurde seit der Suche verändert. Bitte erneut suchen."
                )
            if not dry_run:
                path.unlink()
            status = DeleteStatus.SIMULATED if dry_run else DeleteStatus.DELETED
            return DeleteOutcome(path, year, status)
        except FileNotFoundError as error:
            return DeleteOutcome(path, year, DeleteStatus.MISSING, explain_error(error))
        except (OSError, ValueError) as error:
            return DeleteOutcome(path, year, DeleteStatus.ERROR, explain_error(error))
