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
"""
from __future__ import annotations

import json
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


def load_pinned_versions(project_dir: Path) -> dict[str, str]:
    path = sdk_versions_path(project_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def pin_version(project_dir: Path, package_name: str) -> Optional[str]:
    """package_name의 버전을 프로젝트에 고정한다.

    이미 고정돼 있으면 건드리지 않고 기존 값을 그대로 반환한다("고정"이라는
    이름의 의미 — 최초 1회만 기록, 이후 자동으로 덮어쓰지 않는다). 설치된
    버전을 조회할 수 없으면(패키지 미설치 등) 아무것도 쓰지 않고 None을
    반환한다 — 이 실패가 code_consistency_checker.py의 검증 자체를 막지는
    않는다(그쪽은 importlib.import_module()로 별도 확인).
    """
    pinned = load_pinned_versions(project_dir)
    if package_name in pinned:
        return pinned[package_name]

    installed = resolve_installed_version(package_name)
    if installed is None:
        return None

    pinned[package_name] = installed
    sdk_versions_path(project_dir).write_text(
        json.dumps(pinned, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return installed


def check_version_drift(project_dir: Path, package_name: str) -> Optional[str]:
    """고정된 버전과 현재 설치된 버전이 다르면 경고 문자열을, 같거나 고정
    이력이 없으면 None을 반환한다."""
    pinned = load_pinned_versions(project_dir).get(package_name)
    if pinned is None:
        return None
    installed = resolve_installed_version(package_name)
    if installed is None or installed == pinned:
        return None
    return (
        f"이 프로젝트는 {package_name} {pinned}로 고정됐지만 현재 환경엔 "
        f"{installed}이(가) 설치되어 있습니다 — 코드-본문 정합성 검사가 "
        f"다른 버전을 기준으로 판정될 수 있습니다."
    )
