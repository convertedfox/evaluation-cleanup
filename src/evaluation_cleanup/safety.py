"""Gemeinsame Pfadprüfung ohne Folgen von Links oder Windows-Reparse-Points."""

import stat
from os import stat_result
from pathlib import Path

from evaluation_cleanup.models import FileStamp


class UnsafePathError(ValueError):
    """Ein Pfad erfüllt die Sicherheitsbedingungen nicht."""


def file_stamp(info: stat_result) -> FileStamp:
    """Dateiidentität und Änderungsmerkmale für den Vergleich mit dem Scan."""
    return FileStamp(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def checked_stat(path: Path) -> stat_result:
    """Prüft jede Pfadkomponente mit lstat, bevor weitere Komponenten besucht werden."""
    if not path.is_absolute() or ".." in path.parts:
        raise UnsafePathError("Nur absolute Pfade ohne übergeordnete Pfadsegmente sind erlaubt.")
    components = (*reversed(path.parents), path)
    for component in components:
        info = component.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise UnsafePathError("Verknüpfungen und Windows-Junctions werden übersprungen.")
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise UnsafePathError("Ein übergeordneter Pfad ist kein Verzeichnis.")
    return info


class RootGuard:
    """Bindet eine Operation an einen existierenden, unverknüpften Wurzelordner."""

    def __init__(self, root: Path) -> None:
        info = checked_stat(root)
        if not stat.S_ISDIR(info.st_mode):
            raise UnsafePathError("Der Basisordner ist kein Verzeichnis.")
        self.root = root.resolve(strict=True)
        self.identity = (info.st_dev, info.st_ino)

    def check(self, path: Path) -> stat_result:
        """Prüft Begrenzung und unveränderten Root, bevor der Zielpfad aufgelöst wird."""
        if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(self.root):
            raise UnsafePathError("Der Pfad liegt außerhalb des erlaubten Basisordners.")
        root_info = checked_stat(self.root)
        if (root_info.st_dev, root_info.st_ino) != self.identity:
            raise UnsafePathError("Der Basisordner wurde ausgetauscht. Bitte erneut suchen.")
        info = checked_stat(path)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.root):
            raise UnsafePathError("Der aufgelöste Pfad liegt außerhalb des Basisordners.")
        return info

    def file(self, path: Path) -> FileStamp:
        """Akzeptiert ausschließlich normale Dateien unterhalb des Roots."""
        info = self.check(path)
        if path == self.root or not stat.S_ISREG(info.st_mode):
            raise UnsafePathError("Der Pfad ist keine normale Datei.")
        if info.st_nlink != 1:
            raise UnsafePathError("Dateien mit mehreren Hardlinks werden übersprungen.")
        return file_stamp(info)


def explain_error(error: OSError | ValueError) -> str:
    """Verständliche Fehlertexte, ergänzt um die Betriebssystemdiagnose."""
    if isinstance(error, PermissionError):
        return f"Zugriff verweigert. Bitte Berechtigungen oder geöffnete Dateien prüfen. ({error})"
    if isinstance(error, FileNotFoundError):
        return "Datei oder Ordner ist nicht mehr vorhanden bzw. das Laufwerk nicht erreichbar."
    if isinstance(error, OSError):
        return f"Dateisystemzugriff fehlgeschlagen. Bitte Laufwerk und Verbindung prüfen. ({error})"
    return str(error)
