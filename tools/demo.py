"""Separater Dry-Run-Starter mit Dummy-Dateien oder bereitgestellten Dokumenten.

Dokumenten-Demo: uv run python tools/demo.py --documents
Temporäre Dummy-Demo: uv run python tools/demo.py
Wird nicht in die Windows-Anwendung verpackt und akzeptiert keine fremden Pfade.
"""

import argparse
import stat
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

import flet as ft

from evaluation_cleanup import config
from evaluation_cleanup.app import main
from evaluation_cleanup.deletion import DeletionService
from evaluation_cleanup.safety import checked_stat
from evaluation_cleanup.workflow import CleanupWorkflow

DOCUMENT_LAYOUT = (
    ("Evaluation FührungsSnack Danke_11.7_.xlsx", "2023/05_Führung/FührungsSnack"),
    ("Evaluationen Creative Dates bis Juli 24.xlsx", "2024/03_Kommunikation/Creative Dates"),
    ("Evaluation_Teamrollen_26.11.pdf", "2024/03_Kommunikation/Teamrollen"),
    (
        "Feedbackbögen_DHBW_20240513_Umgang mit schwierigen Menschen.PDF",
        "2024/03_Kommunikation/Umgang mit schwierigen Menschen",
    ),
    ("Feedback_5298.pdf", "2025/99_Demo/Seminar 5298"),
)


def create_document_demo(archive: Path, root: Path) -> tuple[Path, ...]:
    """Kopiert die fünf ZIP-Dokumente in die vereinbarte fiktive Seminarstruktur.

    Liest ausschließlich die explizit erwarteten Archiveinträge; Archivpfade
    werden nie als Zielpfade extrahiert. Vorhandene identische Kopien bleiben
    unverändert, abweichende Dateien und Verknüpfungen werden abgewiesen.
    """
    with ZipFile(archive) as source:
        expected = {name for name, _ in DOCUMENT_LAYOUT}
        if len(source.infolist()) != len(expected) or set(source.namelist()) != expected:
            raise ValueError("Das Archiv muss genau die fünf vereinbarten Demo-Dateien enthalten.")
        # Erst alle Inhalte einschließlich ZIP-Prüfsummen lesen, dann Dateien anlegen.
        documents = tuple(
            (root / folder / name, source.read(name)) for name, folder in DOCUMENT_LAYOUT
        )
    missing: list[tuple[Path, bytes]] = []
    for path, data in documents:
        try:
            info = checked_stat(path)
        except FileNotFoundError:
            missing.append((path, data))
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"Keine eigenständige normale Demo-Datei: {path}")
        if path.read_bytes() != data:
            raise ValueError(
                f"Vorhandene Demo-Datei weicht vom Archiv ab und wird nicht ersetzt: {path}"
            )
    for path, data in missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        checked_stat(path.parent)
        with path.open("xb") as target:
            target.write(data)
    return tuple(path for path, _ in documents)


def create_demo_files(root: Path) -> tuple[Path, ...]:
    """Erzeugt eine kleine Seminarstruktur mit Treffern und bewussten Nicht-Treffern."""
    names = (
        "2022/03_Kommunikation/Konfliktmanagement/Feedback_5298.pdf",
        "2023/05_Führung/FührungsSnack/Evaluation FührungsSnack Danke_11.7_.xlsx",
        "2024/08_Recht und Finanzen/Die Personalratswahl/Unterlagen/Feedbackbögen_Test.PDF",
        "2024/03_Kommunikation/Teamrollen/Evaluation_Teamrollen_26.11.pdf",
        "2024/03_Kommunikation/Creative Dates/Evaluationen Creative Dates bis Juli 24.xlsx",
        "2024/Evaluierung.xls",
        "2024/03_Kommunikation/Teamrollen/Teilnehmerliste.xlsx",
        "2025/05_Führung/Aktuelles Seminar/Feedback.pdf",
        "Vorlagen/Evaluation.pdf",
        "2024_alt/Feedback.pdf",
    )
    paths = []
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "Nur eine Dummy-Datei, keine echte PDF- oder Excel-Datei.", encoding="utf-8"
        )
        paths.append(path)
    return tuple(paths)


def _launch_demo(root: Path, paths: tuple[Path, ...], log_path: Path, title: str) -> None:
    original = {path: path.read_bytes() for path in paths}
    workflow = CleanupWorkflow(DeletionService(root, log_path))

    async def demo_main(page: ft.Page) -> None:
        await main(page, workflow=workflow)
        page.title = title
        page.update()

    ft.run(demo_main)
    if any(not path.is_file() or path.read_bytes() != data for path, data in original.items()):
        raise RuntimeError("Die Demo-Dateien wurden während des Testlaufs verändert.")
    print("Dry-Run geprüft: Alle Demo-Dateien sind unverändert.")


def run_demo(*, documents: bool = False, prepare_only: bool = False) -> None:
    """Startet eine Dry-Run-Demo oder richtet nur die persistente Dokumenten-Demo ein."""
    if config.DELETE_ENABLED:
        raise RuntimeError("Die Demo darf nur mit DELETE_ENABLED = False gestartet werden.")
    if prepare_only and not documents:
        raise ValueError("--prepare-only setzt --documents voraus.")
    if documents:
        development = Path(__file__).resolve().parents[1] / "development"
        base = development / "demo"
        root = base / "Seminare"
        paths = create_document_demo(development / "documents" / "Evaluationen_löschen.zip", root)
        print(f"Dokumenten-Demo mit {len(paths)} Dateien bereit: {root}")
        print("Erwartete Treffer: bis 2023 = 1, bis 2024 = 4, bis 2025 = 5.")
        print(f"Protokoll nach einem Testlauf: {base / 'actions.csv'}")
        if not prepare_only:
            _launch_demo(
                root, paths, base / "actions.csv", "Evaluationen bereinigen – Dokumenten-Demo"
            )
        return
    with TemporaryDirectory(prefix="evaluation-cleanup-demo-") as directory:
        base = Path(directory).resolve()
        root = base / "Seminare"
        paths = create_demo_files(root)
        _launch_demo(root, paths, base / "actions.csv", "Evaluationen bereinigen – lokale Demo")


def cli(argv: Sequence[str] | None = None) -> None:
    """Verarbeitet die Demo-Auswahl; Basisordner und Archiv bleiben fest vorgegeben."""
    parser = argparse.ArgumentParser(description="Evaluationen-Löschtool im Dry-Run testen.")
    parser.add_argument(
        "--documents",
        action="store_true",
        help="Bereitgestellte Dokumente dauerhaft als Demo nutzen.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Dokumenten-Demo nur einrichten, ohne GUI-Start.",
    )
    args = parser.parse_args(argv)
    if args.prepare_only and not args.documents:
        parser.error("--prepare-only setzt --documents voraus.")
    try:
        run_demo(documents=args.documents, prepare_only=args.prepare_only)
    except (OSError, ValueError, RuntimeError, BadZipFile) as error:
        parser.exit(1, f"Demo konnte nicht ausgeführt werden: {error}\n")


if __name__ == "__main__":
    cli()
