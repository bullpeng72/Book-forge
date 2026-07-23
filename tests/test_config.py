"""config.py 기본 동작 테스트."""
from pathlib import Path

from book_forge.config import get_data_dir, resolve_env_path


def test_get_data_dir_under_documents() -> None:
    data_dir = get_data_dir()
    assert data_dir.name == "BookForge"
    assert data_dir.parent.name == "Documents"


def test_resolve_env_path_custom_wins() -> None:
    assert resolve_env_path("/tmp/custom.env") == Path("/tmp/custom.env")


def test_resolve_env_path_default_under_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("BOOK_FORGE_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_env_path()
    assert result == get_data_dir() / ".env"
