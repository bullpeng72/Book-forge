"""agents/sdk_version_pin.py — SDK 버전 고정/드리프트 감지 테스트.

agent_evaluator는 이 테스트 환경에 실제로 설치돼 있으므로(Book-forge의 코어
의존성) 실제 importlib.metadata 조회를 그대로 검증한다.
"""
import json
from pathlib import Path

from book_forge.agents.sdk_version_pin import (
    check_version_drift,
    load_pinned_versions,
    pin_version,
    resolve_installed_version,
    sdk_versions_path,
)


def test_resolve_installed_version_returns_real_version() -> None:
    version = resolve_installed_version("agent_evaluator")
    assert version is not None
    assert version[0].isdigit()


def test_resolve_installed_version_returns_none_for_unknown_package() -> None:
    assert resolve_installed_version("이런_패키지는_없다_xyz") is None


def test_pin_version_creates_sdk_versions_file(tmp_path: Path) -> None:
    pinned = pin_version(tmp_path, "agent_evaluator")
    assert pinned is not None
    assert sdk_versions_path(tmp_path).is_file()
    assert load_pinned_versions(tmp_path) == {"agent_evaluator": pinned}


def test_pin_version_does_not_overwrite_existing_pin(tmp_path: Path) -> None:
    pin_version(tmp_path, "agent_evaluator")  # 실제 설치 버전으로 최초 고정
    # 파일을 직접 다른 값으로 바꾼 뒤 재호출해도 "이미 고정됨"을 그대로 유지해야 한다
    # (최초 1회만 기록 — 현재 설치 버전으로 자동 덮어쓰지 않는다).
    sdk_versions_path(tmp_path).write_text(
        json.dumps({"agent_evaluator": "0.0.1"}), encoding="utf-8"
    )
    second = pin_version(tmp_path, "agent_evaluator")
    assert second == "0.0.1"


def test_pin_version_returns_none_for_unresolvable_package(tmp_path: Path) -> None:
    result = pin_version(tmp_path, "이런_패키지는_없다_xyz")
    assert result is None
    assert not sdk_versions_path(tmp_path).is_file()


def test_load_pinned_versions_returns_empty_dict_when_no_file(tmp_path: Path) -> None:
    assert load_pinned_versions(tmp_path) == {}


def test_load_pinned_versions_returns_empty_dict_on_corrupt_json(tmp_path: Path) -> None:
    sdk_versions_path(tmp_path).write_text("이건 json이 아닙니다", encoding="utf-8")
    assert load_pinned_versions(tmp_path) == {}


def test_check_version_drift_returns_none_when_no_pin_exists(tmp_path: Path) -> None:
    assert check_version_drift(tmp_path, "agent_evaluator") is None


def test_check_version_drift_returns_none_when_versions_match(tmp_path: Path) -> None:
    pin_version(tmp_path, "agent_evaluator")
    assert check_version_drift(tmp_path, "agent_evaluator") is None


def test_check_version_drift_warns_on_mismatch(tmp_path: Path) -> None:
    pin_version(tmp_path, "agent_evaluator")
    sdk_versions_path(tmp_path).write_text(
        json.dumps({"agent_evaluator": "0.0.1"}), encoding="utf-8"
    )
    warning = check_version_drift(tmp_path, "agent_evaluator")
    assert warning is not None
    assert "0.0.1" in warning
    assert "agent_evaluator" in warning
