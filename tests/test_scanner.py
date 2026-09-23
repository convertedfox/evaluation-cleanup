from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from evaluation_cleanup.scanner import inspect_root, is_evaluation, scan


@pytest.mark.parametrize(
    "filename",
    [
        "Evaluation.pdf",
        "EVALUATION.PDF",
        "Evaluation FührungsSnack Danke_11.7_.xlsx",
        "Evaluation_Teamrollen_26.11.pdf",
        "Evaluationen Creative Dates bis Juli 24.xlsx",
        "Feedback_5298.pdf",
        "Feedbackbogen.pdf",
        "Feedbackbögen_DHBW_20240513_Umgang mit schwierigen Menschen.PDF",
        "Feedbackbo\u0308gen.XLSX",
        "Evaluierung.xls",
    ],
)
def test_real_filenames(filename: str) -> None:
    assert is_evaluation(Path(filename))


@pytest.mark.parametrize(
    "filename", ["Teilnehmerliste.xlsx", "Feedback.docx", "Evaluation.pdf.exe"]
)
def test_unrelated_files(filename: str) -> None:
    assert not is_evaluation(Path(filename))


def test_years_are_discovered(root: Path, make_file: Callable[[str], Path]) -> None:
    for name in ("2021", "2024", "2027", "2024_alt", "Vorlagen", "Alt", "２０２５"):
        make_file(f"{name}/Feedback.pdf")
    make_file("2023")  # Vierstelliger Dateiname ist kein Jahresordner.
    result = inspect_root(root)
    assert result.reachable
    assert result.years == (2021, 2024, 2027)


def test_recursive_scan_cutoff_and_metadata(root: Path, make_file: Callable[[str], Path]) -> None:
    deep = make_file("2024/Kategorie/Seminar/Unterordner/tief/Feedback.PDF")
    shallow = make_file("2021/Evaluation.xlsx")
    category_only = make_file("2024/Kategorie/Evaluierung.xls")
    make_file("2025/Kategorie/Seminar/Feedback.pdf")
    make_file("2024/Kategorie/Seminar/Teilnehmerliste.xlsx")
    make_file("Vorlagen/Evaluation.pdf")
    result = scan(2024, root)
    assert result.completed and not result.issues
    by_path = {item.path: item for item in result.candidates}
    assert set(by_path) == {deep, shallow, category_only}
    assert by_path[deep].category == "Kategorie"
    assert by_path[deep].seminar == "Seminar"
    assert by_path[shallow].category == by_path[shallow].seminar == ""
    assert by_path[category_only].category == "Kategorie"
    assert by_path[category_only].seminar == ""
    assert all(path.exists() for path in by_path)


def test_missing_root_and_missing_year(root: Path) -> None:
    assert not inspect_root(root / "missing").reachable
    assert inspect_root(root).years == ()
    with pytest.raises(ValueError, match="nicht mehr vorhanden"):
        scan(2024, root)


@pytest.mark.parametrize("cutoff", [-1, 10000, True])
def test_invalid_cutoff(root: Path, cutoff: int) -> None:
    with pytest.raises(ValueError):
        scan(cutoff, root)


def test_links_are_never_traversed(
    root: Path, tmp_path: Path, make_file: Callable[[str], Path]
) -> None:
    safe = make_file("2024/Feedback.pdf")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Evaluation.pdf").write_text("important")
    try:
        (root / "2023").symlink_to(outside, target_is_directory=True)
        (root / "2024" / "linked").symlink_to(outside, target_is_directory=True)
        (root / "2024" / "Evaluation.pdf").symlink_to(outside / "Evaluation.pdf")
        (root / "2024" / "loop").symlink_to(root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlinks benötigen hier zusätzliche Rechte: {error}")
    result = scan(2024, root)
    assert [item.path for item in result.candidates] == [safe]
    assert len(result.issues) == 4


def test_unreadable_subfolder_is_reported(
    root: Path, make_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    safe = make_file("2024/Feedback.pdf")
    blocked = make_file("2024/blocked/Evaluation.pdf").parent
    original = Path.iterdir

    def iterdir(path: Path) -> Iterator[Path]:
        if path == blocked:
            raise PermissionError("Test: Zugriff verweigert")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    result = scan(2024, root)
    assert [item.path for item in result.candidates] == [safe]
    assert result.issues[0].path == blocked
    assert "Zugriff verweigert" in result.issues[0].message
