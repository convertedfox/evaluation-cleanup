from evaluation_cleanup import config


def test_production_configuration_starts_in_dry_run() -> None:
    assert config.DELETE_ENABLED is False
    assert str(config.ALLOWED_ROOT) == r"T:\ZHL\Personalförderung\02_Seminare"
    assert {".pdf", ".xlsx", ".xls"} == config.SUPPORTED_EXTENSIONS
