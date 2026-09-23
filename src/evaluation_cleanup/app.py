"""Desktop-Einstiegspunkt und Fensterkonfiguration."""

import flet as ft

from evaluation_cleanup.ui import CleanupScreen
from evaluation_cleanup.workflow import CleanupWorkflow


async def main(page: ft.Page, *, workflow: CleanupWorkflow | None = None) -> None:
    """Erstellt genau einen Hauptbildschirm mit unabhängiger Ablaufsteuerung."""
    page.title = "Evaluationen bereinigen"
    page.window.width = 1100
    page.window.height = 780
    page.window.min_width = 720
    page.window.min_height = 640
    page.padding = 20
    screen = CleanupScreen(page, workflow)
    page.add(screen.control)
    await screen.initialize()


def run() -> None:
    """Startet die native Flet-Anwendung."""
    ft.run(main)
