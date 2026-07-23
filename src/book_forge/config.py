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


def ensure_project_dir(slug: str) -> Path:
    """프로젝트 디렉토리(~/Documents/BookForge/projects/<slug>/)를 생성하고 반환한다."""
    project_dir = get_data_dir() / "projects" / slug
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "outputs").mkdir(exist_ok=True)
    (project_dir / "eval_results").mkdir(exist_ok=True)
    return project_dir
