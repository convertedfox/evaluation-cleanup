from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "root"
    path.mkdir()
    return path


@pytest.fixture
def make_file(root: Path) -> Callable[[str], Path]:
    def create(relative: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Dummy evaluation - no real data")
        return path

    return create
