"""실증 가능성 검증 — content_type별 생성 후 정적 검증 (일반 능력 D 강화).

D(실증 가능성 게이트)는 지금까지 C(근거 검증 계층)의 커버리지 임계값을
exercise/diagram 유형에 더 엄격하게 재적용하는 **생성 전** 점검뿐이었다
(draft_cmd.py의 _STRICT_CONTENT_TYPES) — "생성된 결과물이 실제로 검증 가능한
콘텐츠인가"는 생성 후 한 번도 확인하지 않았다. 이 모듈이 그 생성 후 검증을
맡는다:
  - exercise(코드 스니펫) → ast.parse()로 문법 검증. LLM이 생성한 임의 코드를
    자동으로 실행하지는 않는다(부작용·행 없이 안전하게 "실행 가능한 형태인가"의
    최소 근사만 확인 — 실제 실행 검증이 필요하면 저자가 직접 돌려봐야 한다).
  - diagram → mermaid 펜스 블록이 알려진 다이어그램 타입으로 시작하고 실제
    내용(노드/엣지)이 있는지 최소 구조만 확인.
  - reference_table → 표 셀 값이 실제 소스 발췌문에 등장하는 비율을 계산해
    소스에 없는 값을 날조하지 않았는지 대조.
  - capstone → 템플릿 코드에 TODO 마커가 있고(진짜 빈 템플릿인지) 문법이
    유효한지, 정답 코드는 TODO 없이 문법이 유효한 완성 코드인지 확인.

LLM을 호출하지 않는 순수 정적 분석이라 agents/의 다른 모듈과 달리 @agent_eval이
없다 — agent-evaluator의 Gate 점수를 바꾸지 않는, Book-forge 자체 도메인
신호다. 결과는 draft_cmd.py가 ChapterDraftResult에 실어 CLI/배치 요약에 노출만
한다(참고용 — book-forge gate처럼 빌드를 막지 않는다, 기존 Gate C/D 노출과
같은 철학).
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Optional

_CODE_FENCE_RE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_MERMAID_FENCE_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_MERMAID_DIAGRAM_KEYWORDS = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "journey",
    "mindmap",
    "timeline",
)
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
_TABLE_SEPARATOR_RE = re.compile(r"^[-: ]+$")


@dataclass
class VerificationResult:
    content_type: str
    passed: bool
    detail: str
    issues: list = field(default_factory=list)


def verify_exercise_code(draft_md: str) -> VerificationResult:
    """```python 코드 블록의 문법 유효성을 ast.parse()로 확인한다(실행하지 않음)."""
    blocks = _CODE_FENCE_RE.findall(draft_md)
    if not blocks:
        return VerificationResult(
            content_type="exercise",
            passed=False,
            detail="python 코드 블록이 없습니다 — exercise 유형인데 실습 코드가 생성되지 않았습니다.",
        )
    issues = []
    for i, block in enumerate(blocks, 1):
        try:
            ast.parse(block)
        except SyntaxError as exc:
            issues.append(f"코드 블록 {i}: 문법 오류 ({exc.msg}, line {exc.lineno})")
    passed = not issues
    detail = (
        f"코드 블록 {len(blocks)}개 문법 검증 통과"
        if passed
        else f"코드 블록 {len(blocks)}개 중 {len(issues)}개 문법 오류"
    )
    return VerificationResult(content_type="exercise", passed=passed, detail=detail, issues=issues)


_MERMAID_NODE_LABEL_RE = re.compile(r"\[([^\[\]]{2,80})\]")
_IDENTIFIER_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def verify_diagram(
    draft_md: str, sources_text: str = "", *, min_grounding_ratio: float = 0.3
) -> VerificationResult:
    """```mermaid 블록이 있고, 알려진 다이어그램 타입 + 실제 내용을 갖췄는지 확인한다.

    sources_text(일반 능력 U, 옵트인): 주어지면 그래프 노드 라벨에서 뽑은
    식별자가 소스(RAG 청크든 H의 구조 요약이든)에 실제로 등장하는 비율도
    확인한다 — `verify_reference_table()`의 "값이 소스에 있는가" 원칙과
    같다. 다이어그램은 100% LLM이 재구성한 것이라 실제 코드 구조와 무관한
    노드/엣지를 만들어낼 위험이 있다(실측: "패키지 구조" 요청에 파일 1개의
    내부 관계만 그려진 스코프 불일치 사례) — 문법만 보던 기존 검증에 최소
    근거 대조를 추가한다. sources_text가 빈 문자열이면(기존 호출부와
    하위 호환) 이 검사를 건너뛴다.
    """
    blocks = _MERMAID_FENCE_RE.findall(draft_md)
    if not blocks:
        return VerificationResult(
            content_type="diagram",
            passed=False,
            detail="mermaid 코드 블록이 없습니다 — diagram 유형인데 다이어그램이 생성되지 않았습니다.",
        )
    issues = []
    node_labels: list[str] = []
    for i, block in enumerate(blocks, 1):
        lines = [line for line in block.strip().splitlines() if line.strip()]
        first_line = lines[0] if lines else ""
        if not any(first_line.strip().startswith(kw) for kw in _MERMAID_DIAGRAM_KEYWORDS):
            issues.append(
                f"다이어그램 블록 {i}: 알려진 mermaid 타입으로 시작하지 않음 ('{first_line[:30]}')"
            )
        elif len(lines) < 2:
            issues.append(f"다이어그램 블록 {i}: 내용이 비어 있음(타입 선언만 있음)")
        else:
            node_labels.extend(_MERMAID_NODE_LABEL_RE.findall(block))

    if sources_text and node_labels and not issues:
        identifiers = {
            tok for label in node_labels for tok in _IDENTIFIER_TOKEN_RE.findall(label)
        }
        if identifiers:
            grounded = sum(1 for tok in identifiers if tok in sources_text)
            ratio = grounded / len(identifiers)
            if ratio < min_grounding_ratio:
                issues.append(
                    f"노드 라벨의 식별자 {len(identifiers)}개 중 {grounded}개만 소스에서 "
                    f"확인됨({ratio:.0%} < 기준 {min_grounding_ratio:.0%}) — 그래프 구조가 "
                    "소스 근거 없이 만들어졌을 수 있습니다."
                )

    passed = not issues
    detail = (
        f"다이어그램 블록 {len(blocks)}개 구조 검증 통과"
        if passed
        else f"다이어그램 블록 {len(blocks)}개 중 {len(issues)}개 구조 문제"
    )
    return VerificationResult(content_type="diagram", passed=passed, detail=detail, issues=issues)


def verify_reference_table(
    draft_md: str, sources_text: str, *, min_match_ratio: float = 0.5
) -> VerificationResult:
    """표 셀 값이 실제 소스 발췌문에 등장하는 비율을 계산한다(소스에 없는 값 날조 방지)."""
    rows = _TABLE_ROW_RE.findall(draft_md)
    cells = []
    for row in rows:
        for cell in row.split("|"):
            cell = cell.strip().strip("*").strip()
            # 헤더 구분선(---)·너무 짧은 셀(기호류)은 대조 대상에서 제외.
            if len(cell) >= 3 and not _TABLE_SEPARATOR_RE.match(cell):
                cells.append(cell)
    if not cells:
        return VerificationResult(
            content_type="reference_table",
            passed=False,
            detail="대조할 표 셀이 없습니다 — reference_table 유형인데 표가 생성되지 않았습니다.",
        )
    matched = sum(1 for c in cells if c in sources_text)
    ratio = matched / len(cells)
    passed = ratio >= min_match_ratio
    detail = f"표 셀 {len(cells)}개 중 {matched}개({ratio:.0%})가 소스에서 확인됨"
    issues = [] if passed else [f"소스 대조 비율 {ratio:.0%} < 기준 {min_match_ratio:.0%}"]
    return VerificationResult(
        content_type="reference_table", passed=passed, detail=detail, issues=issues
    )


_STRUCTURE_ITEM_NAME_RE = re.compile(r"^- (?:클래스|함수) `([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def verify_module_reference_coverage(draft_md: str, structure_summary: str) -> VerificationResult:
    """T(구조 인덱스 기반 레퍼런스)의 핵심 보장 — `format_structure_summary()`가
    나열한 모든 클래스/함수 이름이 실제로 챕터 본문에 하나도 빠짐없이
    등장하는지 확인한다.

    `verify_reference_table()`의 "값을 지어내지 않았는가"와 반대 방향이다 —
    여기서는 "빠뜨리지 않았는가"를 본다(T의 문제의식은 날조가 아니라 누락).
    이름이 본문 어딘가에 문자열로 등장하기만 하면 통과로 본다(표 셀 안에
    있든 설명 문장 안에 있든 상관없음 — 엄격한 표 구조 검증이 아니라
    "언급이라도 됐는가"의 최소 근사).
    """
    names = sorted(set(_STRUCTURE_ITEM_NAME_RE.findall(structure_summary)))
    if not names:
        return VerificationResult(
            content_type="module_reference",
            passed=True,
            detail="구조 요약에서 대조할 클래스/함수 이름을 찾지 못했습니다.",
        )
    missing = [name for name in names if name not in draft_md]
    passed = not missing
    detail = (
        f"{len(names)}개 항목 모두 본문에 포함됨"
        if passed
        else f"{len(names)}개 항목 중 {len(missing)}개가 본문에서 빠짐"
    )
    issues = [f"`{name}`이(가) 본문에 없습니다." for name in missing]
    return VerificationResult(
        content_type="module_reference", passed=passed, detail=detail, issues=issues
    )


def verify_capstone(template_md: str, solution_md: str) -> VerificationResult:
    """빈 템플릿엔 TODO 마커가 있고 문법이 유효한지, 정답엔 TODO 없이 문법이
    유효한 완성 코드인지 확인한다 — exercise와 달리 두 산출물을 함께 대조한다."""
    if not solution_md.strip():
        return VerificationResult(
            content_type="capstone",
            passed=False,
            detail=(
                "정답이 생성되지 않았습니다 — LLM 응답이 TEMPLATE/SOLUTION "
                "구분자 형식을 지키지 않았습니다."
            ),
        )

    issues: list[str] = []

    template_blocks = _CODE_FENCE_RE.findall(template_md)
    if not template_blocks:
        issues.append("템플릿에 python 코드 블록이 없습니다.")
    else:
        for i, block in enumerate(template_blocks, 1):
            try:
                ast.parse(block)
            except SyntaxError as exc:
                issues.append(f"템플릿 코드 블록 {i}: 문법 오류 ({exc.msg})")
        if not any("TODO" in b.upper() for b in template_blocks):
            issues.append("템플릿 코드에 TODO 마커가 없습니다 — 이미 채워진 정답처럼 보입니다.")

    solution_blocks = _CODE_FENCE_RE.findall(solution_md)
    if not solution_blocks:
        issues.append("정답에 python 코드 블록이 없습니다.")
    else:
        for i, block in enumerate(solution_blocks, 1):
            try:
                ast.parse(block)
            except SyntaxError as exc:
                issues.append(f"정답 코드 블록 {i}: 문법 오류 ({exc.msg})")
        if any("TODO" in b.upper() for b in solution_blocks):
            issues.append("정답 코드에 TODO가 남아있습니다 — 완성되지 않았을 수 있습니다.")

    passed = not issues
    detail = "템플릿/정답 모두 구조 검증 통과" if passed else f"{len(issues)}개 문제 발견"
    return VerificationResult(content_type="capstone", passed=passed, detail=detail, issues=issues)


def verify_demonstration(
    content_type: Optional[str], draft_md: str, sources_text: str
) -> Optional[VerificationResult]:
    """content_type에 맞는 검증기를 실행한다. narrative 등 대응 검증기가 없으면 None.

    capstone은 template/solution 2개 산출물을 함께 봐야 해서 이 단일-문서
    디스패처의 시그니처(draft_md 하나)와 안 맞는다 — draft_cmd.py가
    verify_capstone()을 직접 호출한다."""
    if content_type == "exercise":
        return verify_exercise_code(draft_md)
    if content_type == "diagram":
        return verify_diagram(draft_md, sources_text)
    if content_type == "reference_table":
        return verify_reference_table(draft_md, sources_text)
    if content_type == "module_reference":
        return verify_module_reference_coverage(draft_md, sources_text)
    return None
