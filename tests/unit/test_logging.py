from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from jobscouter.api.routes.control import _redact_line
from jobscouter.core.logging import read_log_lines

# ---------------------------------------------------------------------------
# read_log_lines
# ---------------------------------------------------------------------------


def test_read_log_lines_returns_last_n_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_text("\n".join(f"linha {i}" for i in range(1, 11)))

    with patch("jobscouter.core.logging.LOG_FILE", str(log_file)):
        result = read_log_lines(3)

    assert result == ["linha 8", "linha 9", "linha 10"]


def test_read_log_lines_returns_all_when_n_exceeds_file(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_text("a\nb\nc\n")

    with patch("jobscouter.core.logging.LOG_FILE", str(log_file)):
        result = read_log_lines(100)

    assert result == ["a", "b", "c"]


def test_read_log_lines_strips_trailing_newlines(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_text("linha com espaco  \nlinha normal\n")

    with patch("jobscouter.core.logging.LOG_FILE", str(log_file)):
        result = read_log_lines()

    assert result == ["linha com espaco", "linha normal"]


def test_read_log_lines_returns_empty_when_file_not_found() -> None:
    with patch("jobscouter.core.logging.LOG_FILE", "/tmp/nao_existe_xyzabc.log"):
        result = read_log_lines()

    assert result == []


@pytest.mark.skipif(
    __import__("os").getuid() == 0,
    reason="root ignora permissoes de arquivo",
)
def test_read_log_lines_returns_empty_on_permission_error(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_text("conteudo")
    log_file.chmod(0o000)

    try:
        with patch("jobscouter.core.logging.LOG_FILE", str(log_file)):
            result = read_log_lines()
        assert result == []
    finally:
        log_file.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_read_log_lines_handles_invalid_bytes(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_bytes(b"linha valida\nbytes inv\xe1lidos\n")

    with patch("jobscouter.core.logging.LOG_FILE", str(log_file)):
        result = read_log_lines()

    assert len(result) == 2
    assert result[0] == "linha valida"


# ---------------------------------------------------------------------------
# _redact_line
# ---------------------------------------------------------------------------


def test_redact_postgres_url_with_password() -> None:
    line = "Conectando em postgresql+psycopg://admin:s3cr3t@localhost/db"
    assert "s3cr3t" not in _redact_line(line)
    assert "***" in _redact_line(line)
    assert "localhost/db" in _redact_line(line)


def test_redact_api_key_assignment() -> None:
    line = "gemini_api_key=AIzaSyABCDEFGHIJKLMNOP"
    assert "AIzaSyABCDEFGHIJKLMNOP" not in _redact_line(line)
    assert "***" in _redact_line(line)


def test_redact_token_assignment() -> None:
    assert "meu-token-secreto" not in _redact_line("token=meu-token-secreto")
    assert "meu-token-secreto" not in _redact_line("TOKEN: meu-token-secreto")


def test_redact_bearer_token() -> None:
    line = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload"
    assert "eyJhbGciOiJIUzI1NiJ9.payload" not in _redact_line(line)
    assert "Bearer ***" in _redact_line(line)


def test_redact_does_not_alter_safe_lines() -> None:
    line = "12:00:00 | INFO     | [control.ingest] Concluido | inserted=5 skipped=2"
    assert _redact_line(line) == line
