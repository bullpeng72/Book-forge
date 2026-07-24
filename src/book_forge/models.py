"""M1 데이터 모델 — 기획/목차 파이프라인에서 주고받는 구조체.

TOC(목차)는 사람이 읽는 마크다운과, ScaffoldAgent가 파싱하는 ```toc 매니페스트
블록을 함께 담는다. 이는 Book/AOO가 겪은 문제(읽기 순서가 빌드 스크립트 안에
하드코딩된 ORDERED_FILES 리스트로만 존재)를 선언적 매니페스트로 대체한 것이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from book_forge.exceptions import TocParseError

_TOC_BLOCK_RE = re.compile(r"```toc\s*\n(.*?)```", re.DOTALL)

# 일반 능력 B(콘텐츠 유형 분기) — narrative가 기본값, 나머지는 전용 생성기로 분기된다.
# capstone: exercise("목표→코드→해설" 한 덩어리)와 달리 빈 템플릿(TODO)과 별도
# 정답 파일 2개를 생성한다 — 독자가 실제로 풀어보는 실습/캡스톤 과제 전용.
KNOWN_CONTENT_TYPES = ("narrative", "reference_table", "diagram", "exercise", "capstone")


@dataclass(frozen=True)
class ChapterSpec:
    """목차 한 줄 — Part/Chapter 스캐폴딩에 필요한 최소 정보."""

    part_no: int
    part_title: str
    chapter_no: int
    chapter_title: str
    content_type: str = "narrative"

    @property
    def part_dir_name(self) -> str:
        return f"Part_{self.part_no}_{slugify(self.part_title)}"

    @property
    def chapter_file_name(self) -> str:
        return f"Chapter_{self.chapter_no:02d}_{slugify(self.chapter_title)}.md"


def slugify(text: str) -> str:
    """파일 시스템에 안전한 이름으로 변환한다.

    Python의 str.isalnum()은 한글 음절도 True이므로 한글은 그대로 유지되고,
    공백/구두점만 언더스코어로 정리된다.
    """
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "untitled"


def parse_toc_manifest(toc_markdown: str) -> list[ChapterSpec]:
    """```toc 코드 블록에서 ChapterSpec 목록을 추출한다.

    각 줄 형식: "파트번호|파트제목|챕터번호|챕터제목" (기존 4필드, content_type은
    narrative로 기본 설정) 또는 "파트번호|파트제목|챕터번호|챕터제목|콘텐츠유형"
    (5필드, 일반 능력 B). 5번째 필드가 KNOWN_CONTENT_TYPES에 없는 값이면 예외를
    던지지 않고 narrative로 폴백한다 — LLM이 살짝 다른 표현을 써도 전체 파싱이
    깨지지 않게 하기 위함(slide_condenser.parse_slide_response와 같은 관대한 파싱 원칙).
    """
    match = _TOC_BLOCK_RE.search(toc_markdown)
    if not match:
        raise TocParseError(
            "```toc 코드 블록을 찾을 수 없습니다. LLM 응답이 형식을 지키지 않았을 수 있습니다."
        )

    chapters: list[ChapterSpec] = []
    for line in match.group(1).strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) not in (4, 5):
            raise TocParseError(
                f"목차 항목 형식 오류 (파트번호|파트제목|챕터번호|챕터제목[|콘텐츠유형] 필요): {line!r}"
            )
        part_no_s, part_title, chapter_no_s, chapter_title = parts[:4]
        content_type = "narrative"
        if len(parts) == 5 and parts[4] in KNOWN_CONTENT_TYPES:
            content_type = parts[4]
        try:
            chapters.append(
                ChapterSpec(
                    part_no=int(part_no_s),
                    part_title=part_title,
                    chapter_no=int(chapter_no_s),
                    chapter_title=chapter_title,
                    content_type=content_type,
                )
            )
        except ValueError as exc:
            raise TocParseError(f"파트/챕터 번호가 정수가 아닙니다: {line!r}") from exc

    if not chapters:
        raise TocParseError("```toc 블록이 비어 있습니다.")
    return chapters


_REVISION_LOG_HEADER = "## 개정 이력"
_REVISION_ENTRY_MAX_CHARS = 200
_NEXT_H2_RE = re.compile(r"\n##\s")


def append_toc_revision_entries(
    toc_markdown: str, feedback_entries: list[str], *, today: str | None = None
) -> str:
    """저자 피드백 원문을 목차 파일 맨 위 "## 개정 이력" 섹션에 날짜와 함께 누적한다
    (일반 능력 O, SPEC.md 항목 O — Media/AOO의 목차 개정 이력 관행을 자동화).

    요약은 만들지 않는다(LLM 재호출 없음) — 피드백 원문을 그대로(길면 앞부분만
    잘라) 한 줄로 기록한다. plan_cmd.py가 `run_review_loop(on_feedback=...)`로
    모은, 실제로 개정을 유발한 피드백만 여기 들어온다 — 피드백 없이 바로
    승인된 경우 feedback_entries가 비어 호출 자체가 없다(호출자 책임).
    """
    entry_date = today or date.today().isoformat()
    new_lines = [f"- **{entry_date}**: {_truncate_revision_entry(fb)}" for fb in feedback_entries]

    if _REVISION_LOG_HEADER in toc_markdown:
        header_idx = toc_markdown.index(_REVISION_LOG_HEADER)
        before = toc_markdown[:header_idx]
        after_header = toc_markdown[header_idx + len(_REVISION_LOG_HEADER) :]
        match = _NEXT_H2_RE.search(after_header)
        if match:
            existing_body, rest = after_header[: match.start()], after_header[match.start() :]
        else:
            existing_body, rest = after_header, ""
        rest = rest.lstrip("\n")
        existing_lines = [ln for ln in existing_body.strip("\n").splitlines() if ln]
        merged_lines = existing_lines + new_lines
    else:
        before, rest, merged_lines = "", toc_markdown, new_lines

    lines_block = "\n".join(merged_lines)
    section = _REVISION_LOG_HEADER + (f"\n{lines_block}\n\n" if lines_block else "\n\n")
    return before + section + rest


def _truncate_revision_entry(feedback: str) -> str:
    flat = " ".join(feedback.strip().split())
    if len(flat) <= _REVISION_ENTRY_MAX_CHARS:
        return flat
    return flat[: _REVISION_ENTRY_MAX_CHARS - 1] + "…"
