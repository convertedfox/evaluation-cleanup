"""Unveränderliche Ergebnisse zwischen Dateisystem, Ablaufsteuerung und GUI."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True)
class FileStamp:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class EvaluationCandidate:
    path: Path
    year: int
    category: str
    seminar: str
    filename: str
    stamp: FileStamp


@dataclass(frozen=True)
class FileIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class RootStatus:
    reachable: bool
    years: tuple[int, ...] = ()
    issues: tuple[FileIssue, ...] = ()


@dataclass(frozen=True)
class ScanResult:
    root: Path
    root_identity: tuple[int, int]
    cutoff: int
    candidates: tuple[EvaluationCandidate, ...]
    issues: tuple[FileIssue, ...] = ()
    completed: bool = True


class DeleteStatus(StrEnum):
    DELETED = "OK"
    SIMULATED = "SIMULATED"
    MISSING = "MISSING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DeleteOutcome:
    path: Path
    year: int | None
    status: DeleteStatus
    message: str = ""


@dataclass(frozen=True)
class DeleteReport:
    outcomes: tuple[DeleteOutcome, ...]
    dry_run: bool
    log_path: Path
    log_error: str = ""

    def count(self, status: DeleteStatus) -> int:
        """Anzahl der Dateien mit dem angegebenen Ergebnis."""
        return sum(item.status == status for item in self.outcomes)
