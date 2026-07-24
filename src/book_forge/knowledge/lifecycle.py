"""지식창고 청크를 소스 태그별로 요약한다(Spec J) — `book-forge knowledge status`가 쓴다.

sources.py가 코드/URL 소스를 청크로 만들 때 각 소스 앞에 "# 파일: xxx"/"# 출처: url"
태그를 붙인다(chunk_text 분할 전) — 이 함수는 그 태그를 역으로 파싱해 소스별
청크 수를 센다. 태그가 모든 청크에 남아있다는 보장은 없다(overlap 없이 잘리면
두 번째 이후 청크엔 태그가 안 남을 수 있고, PDF 소스는 애초에 태깅하지 않는다)
— "가능한 범위에서" 집계하는 참고용 요약이지, 정확한 소스 감사 도구가 아니다.
"""
from __future__ import annotations

from book_forge.knowledge.store import KnowledgeStore, _source_label


def summarize_store(store: KnowledgeStore) -> list[tuple[str, int]]:
    """(소스 라벨, 청크 수) 목록을 청크 수 내림차순으로 반환한다.

    태그를 못 찾은 청크는 "(태그 없음)"으로 묶어 목록 맨 끝에 붙인다. Spec K의
    ``query_with_scores(max_per_source=...)``와 같은 태그(``_source_label``)를
    재사용한다 — "소스를 어떻게 식별하는가"는 한 곳에만 정의한다.
    """
    counts: dict[str, int] = {}
    untagged = 0
    for chunk in store.chunks:
        label = _source_label(chunk)
        if label is not None:
            counts[label] = counts.get(label, 0) + 1
        else:
            untagged += 1
    result = sorted(counts.items(), key=lambda kv: -kv[1])
    if untagged:
        result.append(("(태그 없음)", untagged))
    return result
