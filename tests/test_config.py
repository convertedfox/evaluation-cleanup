from evaluation_cleanup import config


def test_production_configuration_is_released_for_real_deletion() -> None:
    assert config.DELETE_ENABLED is True
    assert str(config.ALLOWED_ROOT) == r"T:\ZHL\Personalförderung\02_Seminare"
    assert {".pdf", ".xlsx", ".xls"} == config.SUPPORTED_EXTENSIONS
