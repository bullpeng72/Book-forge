"""챕터 간 기술 용어 표기 일관성 검사 (일반 능력 AK, SPEC.md 4부).

각 챕터가 독립된 LLM 호출 + 독립된 RAG 컨텍스트로 생성되므로, 같은 대상을
챕터마다 다른 표기(`ToolCallAnalyzer` vs `tool_call_analyzer` vs
`Tool-Call-Analyzer`)로 부를 위험이 구조적으로 있다 — 이 세션에서 배치
재생성 중 서로 무관한 챕터가 같은 소스 내용으로 드리프트하는 사례를 실제로
관찰하며 확인된 문제다.

**범위를 의도적으로 좁혔다**: 전체 도서 대상의 정교한 NLP 기반 동의어 탐지
(예: "Gate" vs "게이트" 같은 한국어-영어 개념 매칭)는 과설계 위험이 크다.
대신 이미 검증된 `code_consistency_checker._BACKTICK_RE`/`_BUILTIN_EXCLUSIONS`를
재사용해, 백틱으로 감싼 기술 용어만 뽑고 대소문자·구두점을 제거한 "접힌 키"가
같은데 실제 표기가 챕터마다 다른 경우만 후보로 보고한다 — 구조적으로 결정
가능한 것만 다루고, 자동으로 통일하지 않는다(저자가 최종 판단).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from book_forge.agents.code_consistency_checker import _BACKTICK_RE, _BUILTIN_EXCLUSIONS

_MIN_TERM_LENGTH = 3


def _fold_key(term: str) -> str:
    """대소문자·구두점을 지운 "접힌" 형태 — 같은 개념의 서로 다른 표기를 묶는 키."""
    return "".join(ch for ch in term.lower() if ch.isalnum())


def _extract_terms(text: str) -> list[str]:
    """챕터 본문에서 백틱 기술 용어를 챕터 내 중복 없이 순서대로 뽑는다."""
    seen: list[str] = []
    for name in _BACKTICK_RE.findall(text):
        base = name.split(".")[0]
        if base in _BUILTIN_EXCLUSIONS or len(base) < _MIN_TERM_LENGTH:
            continue
        if name not in seen:
            seen.append(name)
    return seen


@dataclass
class TermVariantGroup:
    """같은 "접힌 키"로 묶이지만 실제 표기가 2가지 이상인 후보 하나."""

    fold_key: str
    variants: dict[str, list[str]] = field(default_factory=dict)  # 표기 -> 등장 챕터 라벨 목록


def find_term_variants(chapters: list[tuple[str, str]]) -> list[TermVariantGroup]:
    """chapters: (챕터 라벨, 본문) 쌍 목록.

    반환값은 fold_key 기준 정렬된 표기 불일치 후보 목록 — 표기가 정확히 하나뿐인
    (즉, 이미 일관된) 용어는 결과에 포함하지 않는다.
    """
    buckets: dict[str, dict[str, list[str]]] = {}
    for label, text in chapters:
        for term in _extract_terms(text):
            key = _fold_key(term)
            variant_labels = buckets.setdefault(key, {}).setdefault(term, [])
            if label not in variant_labels:
                variant_labels.append(label)

    groups = [
        TermVariantGroup(fold_key=key, variants=variants)
        for key, variants in buckets.items()
        if len(variants) >= 2
    ]
    groups.sort(key=lambda g: g.fold_key)
    return groups
