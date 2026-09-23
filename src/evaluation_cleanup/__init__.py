"""Windows-Desktop-Werkzeug zur kontrollierten Bereinigung alter Evaluationen."""


def main() -> None:
    """Startet die Anwendung über den bestehenden Konsolen-Einstiegspunkt."""
    from evaluation_cleanup.app import run

    run()
