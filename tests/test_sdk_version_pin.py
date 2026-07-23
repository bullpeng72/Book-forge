"""agents/sdk_version_pin.py — SDK 버전 고정/드리프트 감지 테스트.

agent_evaluator는 이 테스트 환경에 실제로 설치돼 있으므로(Book-forge의 코어
의존성) 실제 importlib.metadata 조회를 그대로 검증한다. 로컬 코드베이스
대상(일반 능력 I) 테스트는 실제 git 저장소를 tmp_path에 만들어 검증한다.
"""
import json
import subprocess
from pathlib import Path

from book_forge.agents.sdk_version_pin import (
    check_version_drift,
    load_pinned_versions,
    pin_version,
    resolve_installed_version,
    resolve_local_version,
    resolve_version,
    sdk_versions_path,
)


def _init_git_repo(directory: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=directory, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=directory, check=True)
    (directory / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=directory, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=directory, check=True)


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


# ── 로컬 코드베이스 대상(일반 능력 I) ────────────────────────────────────────


def test_resolve_local_version_returns_short_commit_hash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    version = resolve_local_version(repo)
    assert version is not None
    assert "-dirty" not in version
    assert len(version) >= 6  # git --short 해시는 보통 7자 내외


def test_resolve_local_version_flags_dirty_working_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")  # 커밋 안 된 변경
    version = resolve_local_version(repo)
    assert version is not None
    assert version.endswith("-dirty")


def test_resolve_local_version_returns_none_for_non_git_directory(tmp_path: Path) -> None:
    non_git = tmp_path / "plain"
    non_git.mkdir()
    assert resolve_local_version(non_git) is None


def test_resolve_version_dispatches_by_directory_vs_package_name(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    local_result = resolve_version(str(repo))
    assert local_result is not None
    assert "-dirty" not in local_result

    package_result = resolve_version("agent_evaluator")
    assert package_result is not None
    assert package_result[0].isdigit()


def test_pin_version_works_for_local_git_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    pinned = pin_version(project_dir, str(repo))
    assert pinned is not None

    key = str(repo.resolve())
    assert load_pinned_versions(project_dir) == {key: pinned}


def test_pin_version_normalizes_relative_and_absolute_local_paths_to_same_key(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    pin_version(project_dir, str(repo))
    # 절대 경로로 다시 호출해도 같은 키를 재사용해야 한다(중복 기록 방지).
    second = pin_version(project_dir, str(repo.resolve()))
    assert len(load_pinned_versions(project_dir)) == 1
    assert second == load_pinned_versions(project_dir)[str(repo.resolve())]


def test_pin_version_returns_none_for_non_git_local_directory(tmp_path: Path) -> None:
    non_git = tmp_path / "plain"
    non_git.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = pin_version(project_dir, str(non_git))
    assert result is None
    assert not sdk_versions_path(project_dir).is_file()


def test_check_version_drift_detects_new_commit_on_local_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    pin_version(project_dir, str(repo))
    # 새 커밋을 추가해 git 상태를 바꾼다.
    (repo / "b.py").write_text("y = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "b.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=repo, check=True)

    warning = check_version_drift(project_dir, str(repo))
    assert warning is not None
    assert str(repo) in warning
