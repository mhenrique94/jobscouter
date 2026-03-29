from __future__ import annotations

import importlib

import pytest

import jobscouter.api.main as api_main_module
import jobscouter.core.config as config_module


def _load_app_for_env(monkeypatch: pytest.MonkeyPatch, app_env: str):
    monkeypatch.setenv("APP_ENV", app_env)

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    reloaded_main = importlib.reload(api_main_module)
    return reloaded_main.app


@pytest.mark.parametrize(
    ("app_env", "expected_docs", "expected_openapi", "expected_redoc"),
    [
        ("development", "/docs", "/openapi.json", "/redoc"),
        ("production", None, None, None),
        ("prod", None, None, None),
    ],
)
def test_docs_and_schema_urls_follow_app_env(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    expected_docs: str | None,
    expected_openapi: str | None,
    expected_redoc: str | None,
) -> None:
    app = _load_app_for_env(monkeypatch, app_env)

    assert app.docs_url == expected_docs
    assert app.openapi_url == expected_openapi
    assert app.redoc_url == expected_redoc
