"""책 끝 찾아보기(색인) 생성 (일반 능력 AL, SPEC.md 4부).

실제 기술 서적은 대부분 끝에 키워드→위치 찾아보기가 있는데 Book-forge에는
그 개념이 전혀 없었다. 새 추출 규칙을 또 만들지 않고 AK(`term_consistency_checker`)가
이미 검증한 백틱 기술 용어 추출(`_extract_terms`)을 그대로 재사용한다.

PDF는 챕터별 개별 파일 구조라(도서 전체를 한 파일로 묶는 개념이 없음) 파일을
가로지르는 실제 페이지 번호를 매길 수 없다 — "가능하면 페이지 번호"라는 SPEC
문구를 이 아키텍처 제약 안에서 정직하게 절충해, 위치 정보로 챕터 번호/제목을
쓴다(HTML은 같은 이유로 애초에 페이지 개념이 없어 챕터 앵커 링크를 쓴다 —
SPEC이 명시한 대로).
"""
from __future__ import annotations

from dataclasses import dataclass

from book_forge.agents.term_consistency_checker import _extract_terms
from book_forge.publish.toc_loader import ResolvedChapter


@dataclass(frozen=True)
class IndexEntry:
    term: str
    chapters: list[ResolvedChapter]


def build_index_entries(chapters: list[ResolvedChapter]) -> list[IndexEntry]:
    """용어(가나다/알파벳 순) -> 등장하는 챕터 목록. 존재하지 않는 챕터 파일은 건너뛴다."""
    buckets: dict[str, list[ResolvedChapter]] = {}
    for rc in chapters:
        if not rc.exists:
            continue
        text = rc.path.read_text(encoding="utf-8")
        for term in _extract_terms(text):
            bucket = buckets.setdefault(term, [])
            if rc not in bucket:
                bucket.append(rc)

    return [
        IndexEntry(term=term, chapters=chs)
        for term, chs in sorted(buckets.items(), key=lambda kv: kv[0].lower())
    ]
