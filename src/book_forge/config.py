"""Book-forge 설정 및 사용자 데이터 디렉토리 관리.

Lecture_forge의 ``~/Documents/LectureForge/`` 관례를 그대로 따른다 — 사용자가
Finder/탐색기에서 바로 접근 가능한 일반 폴더에 .env와 프로젝트 산출물을 둔다.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

APP_DIR_NAME = "BookForge"


def get_data_dir() -> Path:
    """플랫폼별 기본 데이터 디렉토리 (~/Documents/BookForge/)."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    else:
        base = Path.home()
    return base / "Documents" / APP_DIR_NAME


def resolve_env_path(custom_path: Optional[str] = None) -> Path:
    """.env 파일 경로를 우선순위대로 탐색한다.

    1. custom_path 인자
    2. BOOK_FORGE_ENV_FILE 환경변수
    3. ./.env (현재 디렉토리)
    4. ~/Documents/BookForge/.env (기본)
    """
    if custom_path:
        return Path(custom_path)

    env_var = os.environ.get("BOOK_FORGE_ENV_FILE")
    if env_var:
        return Path(env_var)

    local_env = Path.cwd() / ".env"
    if local_env.exists():
        return local_env

    return get_data_dir() / ".env"


def load_config(env_path: Optional[str] = None) -> Path:
    """.env를 로드하고 실제 사용된 경로를 반환한다. 파일이 없어도 예외를 던지지 않는다."""
    path = resolve_env_path(env_path)
    if path.exists():
        load_dotenv(dotenv_path=path)
    return path


def project_dir_for(slug: str) -> Path:
    """ensure_project_dir()과 같은 경로 계산이지만 디렉토리를 만들지 않는다.

    일반 능력 AH — 새 프로젝트를 만들기 전에 "이미 존재하는가"만 확인하고
    싶은 호출부(new_cmd.py의 슬러그 충돌 경고)를 위한 조회 전용 헬퍼다.
    `get_data_dir()`를 이 모듈(config.py) 안에서 호출해야 테스트의
    `monkeypatch.setattr(config_module, "get_data_dir", ...)`가 그대로
    적용된다 — 호출부가 `get_data_dir`을 직접 import해서 쓰면 import 시점에
    스냅샷된 별도 바인딩이라 몽키패치가 반영되지 않는다(실제로 이 문제를
    피하려고 이 헬퍼를 만들었다).
    """
    return get_data_dir() / "projects" / slug


def ensure_project_dir(slug: str) -> Path:
    """프로젝트 디렉토리(~/Documents/BookForge/projects/<slug>/)를 생성하고 반환한다."""
    project_dir = project_dir_for(slug)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "outputs").mkdir(exist_ok=True)
    (project_dir / "eval_results").mkdir(exist_ok=True)
    return project_dir
