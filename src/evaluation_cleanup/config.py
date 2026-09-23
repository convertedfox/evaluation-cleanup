"""Zentrale, bewusst nicht über die Oberfläche editierbare Konfiguration."""

from pathlib import Path
from typing import Final

ALLOWED_ROOT: Final = Path(r"T:\ZHL\Personalförderung\02_Seminare")
DELETE_ENABLED: Final = False
EVALUATION_KEYWORDS: Final = (
    "evaluation",
    "evaluierung",
    "feedback",
    "feedbackbogen",
    "feedbackbögen",
)
SUPPORTED_EXTENSIONS: Final = frozenset({".pdf", ".xlsx", ".xls"})
