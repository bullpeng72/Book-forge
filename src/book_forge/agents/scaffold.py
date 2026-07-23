"""ScaffoldAgent — 승인된 목차(ChapterSpec 목록) → Part/Chapter MD 스캐폴드 생성.

파일 쓰기는 "사후 채점"이 아니라 "실행 전 차단"이 맞는 성격이라 @agent_eval이
아니라 @tool_guard + live_guardrail_session을 쓴다.

주의 — 정확히 밝혀둘 것: ``ScopeConfig``는 파일 경로가 아니라 *도구 이름*
allow/forbid 목록이다 (agent_evaluator/gates/gate_b_behavioral/configs.py 확인
완료). 즉 "프로젝트 디렉토리 밖 쓰기 금지"는 Harness Config가 대신 해주는
기능이 아니라 이 모듈이 직접 구현하는 방어 코드다. LiveGuardrail이 실제로
막아주는 것은 ``LoopDetectionConfig`` 기반의 폭주(동일 호출 반복) 탐지뿐이다.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from agent_evaluator import LoopDetectionConfig
from agent_evaluator.gates.live_guardrail import LiveGuardrail, live_guardrail_session, tool_guard

from book_forge.exceptions import BookForgeError
from book_forge.models import ChapterSpec
from book_forge.publish.toc_loader import ResolvedChapter

CHAPTER_TEMPLATE = """# Chapter {chapter_no:02d}: {chapter_title}

> TODO: 이 챕터를 집필하세요.
"""


@tool_guard(audit_blocked=True)
def write_chapter_stub(
    project_dir: str,
    part_dir_name: str,
    chapter_file_name: str,
    chapter_no: int,
    chapter_title: str,
) -> str:
    """단일 챕터 스텁 파일 + images/ 디렉토리를 생성한다.

    인자를 원시 타입(str/int)만 받는 이유: LiveGuardrail 내부 로직이 도구
    호출 인자를 로깅/직렬화할 수 있어, 임의의 dataclass보다 JSON-safe한
    값만 넘기는 편이 안전하다.
    """
    project_path = Path(project_dir)
    part_path = project_path / part_dir_name
    chapter_path = part_path / chapter_file_name

    resolved_project = project_path.resolve()
    resolved_target = chapter_path.resolve()
    if resolved_project not in resolved_target.parents:
        raise BookForgeError(f"프로젝트 디렉토리 밖 경로 쓰기 시도 차단: {resolved_target}")

    part_path.mkdir(parents=True, exist_ok=True)
    (part_path / "images").mkdir(exist_ok=True)

    if chapter_path.exists():
        return f"skipped (exists): {chapter_path}"

    chapter_path.write_text(
        CHAPTER_TEMPLATE.format(chapter_no=chapter_no, chapter_title=chapter_title),
        encoding="utf-8",
    )
    return f"created: {chapter_path}"


def scaffold_project(project_dir: Path, chapters: list[ChapterSpec]) -> list[str]:
    """승인된 목차 전체를 스캐폴딩한다. 세션 하나로 묶어 loop_detection이 작동하게 한다."""
    guardrail = LiveGuardrail(loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=5))
    results: list[str] = []
    with live_guardrail_session(guardrail, task_id=f"scaffold_{project_dir.name}"):
        for spec in chapters:
            results.append(
                write_chapter_stub(
                    str(project_dir),
                    spec.part_dir_name,
                    spec.chapter_file_name,
                    spec.chapter_no,
                    spec.chapter_title,
                )
            )
    return results


@dataclass
class ReconcileResult:
    created: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


def _assert_within_project(project_dir: Path, target: Path) -> None:
    resolved_project = project_dir.resolve()
    resolved_target = target.resolve()
    if resolved_project not in resolved_target.parents:
        raise BookForgeError(f"프로젝트 디렉토리 밖 경로 접근 시도 차단: {resolved_target}")


def reconcile_chapters(
    project_dir: Path,
    old_chapters: list[ResolvedChapter],
    new_specs: list[ChapterSpec],
) -> ReconcileResult:
    """목차 개정(``plan --revise``) 후 챕터 파일을 재조정한다.

    챕터 번호(``chapter_no``)를 저자가 이미 쓴 내용의 식별자로 삼는다 — 안정된
    챕터 ID가 없으므로 "저자가 기존 챕터 순서를 재배열하지 않고 앞/뒤에 추가·삭제만
    한다"는 가정이 깔려 있다(알려진 한계, README에 명시).

    - 새 스펙의 경로에 이미 파일이 있으면 손대지 않는다(저자 집필 내용 보존).
    - 같은 chapter_no의 옛 챕터가 존재하고 제목이 바뀌어 경로만 달라졌다면, 내용을
      새 경로로 이동한다(재생성해 내용을 날리지 않음) — images/도 함께 옮긴다.
    - 새 목차에서 완전히 빠진 chapter_no는 파일을 **삭제하지 않고** orphaned로만 보고한다.
    """
    old_by_no = {rc.spec.chapter_no: rc for rc in old_chapters}
    new_nos = {spec.chapter_no for spec in new_specs}
    result = ReconcileResult()

    guardrail = LiveGuardrail(loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=5))
    with live_guardrail_session(guardrail, task_id=f"reconcile_{project_dir.name}"):
        for spec in new_specs:
            new_path = project_dir / spec.part_dir_name / spec.chapter_file_name
            _assert_within_project(project_dir, new_path)
            if new_path.exists():
                continue

            old_rc = old_by_no.get(spec.chapter_no)
            if old_rc is not None and old_rc.exists and old_rc.path != new_path:
                _assert_within_project(project_dir, old_rc.path)
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_images = new_path.parent / "images"
                new_images.mkdir(exist_ok=True)
                old_images = old_rc.path.parent / "images"
                if old_images.is_dir() and old_images != new_images:
                    for img in old_images.iterdir():
                        shutil.copy2(img, new_images / img.name)
                old_rc.path.rename(new_path)
                result.renamed.append((str(old_rc.path), str(new_path)))
            else:
                outcome = write_chapter_stub(
                    str(project_dir),
                    spec.part_dir_name,
                    spec.chapter_file_name,
                    spec.chapter_no,
                    spec.chapter_title,
                )
                if outcome.startswith("created"):
                    result.created.append(str(new_path))

        for old_no, rc in old_by_no.items():
            if old_no not in new_nos and rc.exists:
                result.orphaned.append(str(rc.path))

    return result
