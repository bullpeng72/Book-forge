"""SDK 버전 고정 메타데이터 — 프로젝트가 코드-본문 정합성 검사(C 확장,
`code_consistency_checker.py`)의 기준으로 삼는 패키지 버전을 프로젝트에 기록한다
(9개 후보 기능의 5번).

`book-forge draft ... --check-package agent_evaluator`는 지금까지 "그 순간
설치된" 버전을 암묵적으로 기준 삼아왔다 — 오늘 0.9.9로 챕터를 쓰고 몇 달 뒤
환경이 1.2.0으로 올라간 채로 같은 프로젝트에 `--check-package`를 다시 돌리면,
검증 결과가 "본문이 틀렸다"가 아니라 "SDK가 바뀌었다"는 걸 의미할 수도 있는데
이 둘을 구분할 방법이 없었다. 이 모듈이 프로젝트별로 `sdk_versions.json`에
"이 프로젝트가 실제로 기준 삼은 버전"을 한 번 고정해두고, 이후 호출마다 현재
설치된 버전과 대조해 드리프트를 알린다.

Book/AOO의 `build_book.py`가 `pyproject.toml`에서 버전을 자동으로 읽어 표지에
찍던 관례를 Book-forge에 맞게 재해석한 것이다 — Book-forge 자신의 버전이
아니라, 저자가 챕터 근거로 삼는 **대상 SDK**의 버전을 고정한다는 점이 다르다.

로컬 코드베이스 대상(일반 능력 I): package_name이 실제 로컬 디렉토리면 설치된
패키지가 아니므로 `importlib.metadata.version()`으로 조회할 버전 번호 자체가
없다. 대신 git 저장소면 커밋 해시(짧게)+dirty 여부를 버전 대용으로 쓴다 —
agent-evaluator 자신의 `agent_version="auto"`(git 커밋+dirty 해시) 패턴과
같은 원리다. git이 없거나 저장소가 아니면 버전 추적 없이 조용히 스킵한다
(코드-본문 정합성 검사 자체는 계속 정상 동작 — 버전 고정은 부가 기능).
"""
from __future__ import annotations

import json
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional


def sdk_versions_path(project_dir: Path) -> Path:
    return project_dir / "sdk_versions.json"


def resolve_installed_version(package_name: str) -> Optional[str]:
    """현재 환경에 설치된 package_name의 버전을 조회한다. 미설치/조회 불가 시 None."""
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def resolve_local_version(directory: Path) -> Optional[str]:
    """디렉토리가 git 저장소면 커밋 해시(짧게)+dirty 여부를 버전 대용으로
    반환한다. git이 없거나 저장소가 아니면(또는 명령 실패/타임아웃) None —
    예외를 던지지 않고 "버전 추적 불가"로 조용히 처리한다."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if commit.returncode != 0:
            return None
        status = subprocess.run(
            ["git", "-C", str(directory), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        suffix = "-dirty" if status.stdout.strip() else ""
        return f"{commit.stdout.strip()}{suffix}"
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolve_version(target: str) -> Optional[str]:
    """target이 로컬 디렉토리면 git 기준 버전을, 아니면 설치된 패키지 버전을
    조회한다 — pin_version()/check_version_drift()가 공유하는 디스패치 지점."""
    local_dir = Path(target)
    if local_dir.is_dir():
        return resolve_local_version(local_dir)
    return resolve_installed_version(target)


def load_pinned_versions(project_dir: Path) -> dict[str, str]:
    path = sdk_versions_path(project_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_target_key(target: str) -> str:
    """package_name은 그대로, 로컬 디렉토리는 절대 경로로 정규화해 dict 키로
    쓴다 — `./agents`와 `src/book_forge/agents`처럼 상대 경로를 다르게 써도
    같은 디렉토리를 가리키면 같은 고정 기록을 재사용하게 하기 위함."""
    local_dir = Path(target)
    if local_dir.is_dir():
        return str(local_dir.resolve())
    return target


def pin_version(project_dir: Path, package_name: str) -> Optional[str]:
    """package_name(설치된 패키지명 또는 로컬 디렉토리 경로)의 버전을
    프로젝트에 고정한다.

    이미 고정돼 있으면 건드리지 않고 기존 값을 그대로 반환한다("고정"이라는
    이름의 의미 — 최초 1회만 기록, 이후 자동으로 덮어쓰지 않는다). 버전을
    조회할 수 없으면(패키지 미설치, 로컬 디렉토리인데 git 저장소가 아님 등)
    아무것도 쓰지 않고 None을 반환한다 — 이 실패가 code_consistency_checker.py의
    검증 자체를 막지는 않는다(그쪽은 importlib/정적 분석으로 별도 확인).
    """
    key = _normalize_target_key(package_name)
    pinned = load_pinned_versions(project_dir)
    if key in pinned:
        return pinned[key]

    resolved = resolve_version(package_name)
    if resolved is None:
        return None

    pinned[key] = resolved
    sdk_versions_path(project_dir).write_text(
        json.dumps(pinned, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return resolved


def check_version_drift(project_dir: Path, package_name: str) -> Optional[str]:
    """고정된 버전과 현재(설치된/git) 버전이 다르면 경고 문자열을, 같거나 고정
    이력이 없으면 None을 반환한다."""
    key = _normalize_target_key(package_name)
    pinned = load_pinned_versions(project_dir).get(key)
    if pinned is None:
        return None
    current = resolve_version(package_name)
    if current is None or current == pinned:
        return None
    return (
        f"이 프로젝트는 {package_name} {pinned}로 고정됐지만 현재는 "
        f"{current}입니다 — 코드-본문 정합성 검사가 다른 버전/커밋을 "
        f"기준으로 판정될 수 있습니다."
    )
