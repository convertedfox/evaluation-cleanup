"""Ausschließlich lesende Jahreserkennung und rekursive Dateinamensuche."""

import re
import stat
import unicodedata
from pathlib import Path

from evaluation_cleanup import config
from evaluation_cleanup.models import EvaluationCandidate, FileIssue, RootStatus, ScanResult
from evaluation_cleanup.safety import RootGuard, UnsafePathError, explain_error


def is_evaluation(path: Path) -> bool:
    """Erkennt unterstützte Dateien anhand Unicode-normalisierter Dateinamen."""
    name = unicodedata.normalize("NFKC", path.stem).casefold()
    return path.suffix.casefold() in config.SUPPORTED_EXTENSIONS and any(
        unicodedata.normalize("NFKC", word).casefold() in name
        for word in config.EVALUATION_KEYWORDS
    )


def _year_directories(guard: RootGuard) -> tuple[list[tuple[int, Path]], list[FileIssue]]:
    years: list[tuple[int, Path]] = []
    issues: list[FileIssue] = []
    guard.check(guard.root)
    for path in sorted(guard.root.iterdir()):
        if not re.fullmatch(r"[0-9]{4}", path.name):
            continue
        try:
            if stat.S_ISDIR(guard.check(path).st_mode):
                years.append((int(path.name), path))
        except (OSError, ValueError) as error:
            issues.append(FileIssue(path, explain_error(error)))
    return years, issues


def inspect_root(root: Path = config.ALLOWED_ROOT) -> RootStatus:
    """Prüft Erreichbarkeit und entdeckt direkt untergeordnete Jahresordner."""
    try:
        years, issues = _year_directories(RootGuard(root))
        return RootStatus(True, tuple(year for year, _ in years), tuple(issues))
    except (OSError, ValueError) as error:
        return RootStatus(False, issues=(FileIssue(root, explain_error(error)),))


def scan(cutoff: int, root: Path = config.ALLOWED_ROOT) -> ScanResult:
    """Durchsucht alle vorhandenen Jahresordner bis zum Grenzjahr ohne Linkverfolgung.

    Übersprungene Pfade werden als Hinweise zurückgegeben. Ein nicht erreichbarer
    oder während des Scans ausgetauschter Root bricht den Scan mit einer Exception ab.
    """
    if type(cutoff) is not int or not 0 <= cutoff <= 9999:
        raise ValueError("Bitte ein gültiges vierstelliges Jahr auswählen.")
    guard = RootGuard(root)
    years, issues = _year_directories(guard)
    if cutoff not in {year for year, _ in years}:
        raise ValueError("Der ausgewählte Jahresordner ist nicht mehr vorhanden.")
    candidates: list[EvaluationCandidate] = []
    pending = [(year, path) for year, path in years if year <= cutoff]
    while pending:
        year, directory = pending.pop()
        try:
            if not stat.S_ISDIR(guard.check(directory).st_mode):
                raise UnsafePathError("Der Ordner wurde während der Suche verändert.")
            entries = sorted(directory.iterdir())
        except (OSError, ValueError) as error:
            issues.append(FileIssue(directory, explain_error(error)))
            continue
        for path in entries:
            try:
                info = guard.check(path)
                if stat.S_ISDIR(info.st_mode):
                    pending.append((year, path))
                elif is_evaluation(path):
                    stamp = guard.file(path)
                    parts = path.relative_to(guard.root).parts
                    candidates.append(
                        EvaluationCandidate(
                            path=path,
                            year=year,
                            category=parts[1] if len(parts) >= 3 else "",
                            seminar=parts[2] if len(parts) >= 4 else "",
                            filename=path.name,
                            stamp=stamp,
                        )
                    )
            except (OSError, ValueError) as error:
                issues.append(FileIssue(path, explain_error(error)))
    guard.check(guard.root)
    candidates.sort(key=lambda item: (-item.year, str(item.path).casefold()))
    return ScanResult(guard.root, guard.identity, cutoff, tuple(candidates), tuple(issues))
