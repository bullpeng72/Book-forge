"""도서 전면부(front matter) 메타데이터 — 저자·저작권·판(edition) 정보
(일반 능력 AI, SPEC.md 4부).

`00_기획안.md`에 저자명을 끼워 넣는 대신 별도 JSON 파일로 둔 이유: 기획안은
`PlannerAgent`가 생성한 순수 프로즈(`## 목적`으로 시작)와 `new_cmd.py`가 저장
시점에 붙이는 `# {title}\n\n` 접두어만으로 구성된다는 계약이 이미 있고
(`plan_cmd.py::_strip_title_h1()`이 정확히 이 형식을 가정해 접두어를 벗겨낸
뒤 다시 리뷰 루프에 넣는다). 저자명 한 줄을 그 사이에 끼워 넣으면 이 계약이
깨진다 — 완전히 별도 파일로 분리하면 기존 기획안 파싱/리뷰 로직을 전혀
건드리지 않는다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_FRONT_MATTER_FILENAME = "front_matter.json"


@dataclass(frozen=True)
class FrontMatter:
    author: str = ""
    license_notice: str = ""
    edition: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.author or self.license_notice or self.edition)


def front_matter_path(project_dir: Path) -> Path:
    return project_dir / _FRONT_MATTER_FILENAME


def load_front_matter(project_dir: Path) -> FrontMatter:
    """front_matter.json이 없으면(대부분의 기존/단순 프로젝트) 빈 FrontMatter를
    반환한다 — 표지 페이지 렌더링 쪽에서 `is_empty`로 건너뛸 수 있게."""
    path = front_matter_path(project_dir)
    if not path.is_file():
        return FrontMatter()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return FrontMatter()
    return FrontMatter(
        author=data.get("author", ""),
        license_notice=data.get("license_notice", ""),
        edition=data.get("edition", ""),
    )


def save_front_matter(project_dir: Path, front_matter: FrontMatter) -> None:
    if front_matter.is_empty:
        return  # 아무 필드도 없으면 빈 파일을 만들 이유가 없다.
    front_matter_path(project_dir).write_text(
        json.dumps(asdict(front_matter), ensure_ascii=False, indent=2), encoding="utf-8"
    )
