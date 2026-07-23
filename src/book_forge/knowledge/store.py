"""인메모리 코사인 유사도 지식창고 — 벡터 DB 프로세스 없이 numpy만으로 충분한 규모.

챕터 한 편의 집필 보조에 필요한 소스 규모(PDF 몇 개~수십 개 청크)에는 ChromaDB
같은 별도 벡터 DB가 과한 인프라라는 판단 — 별도 프로세스나 스키마 없이 평범한
JSON 파일 하나로 저장/로드한다(일반 능력 E: `book-forge chat`이 draft 세션이
끝난 뒤에도 같은 소스로 계속 질의할 수 있게).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from book_forge.knowledge.embeddings import embed_text, embed_texts


def default_store_path(project_dir: Path) -> Path:
    """draft/chat이 공유하는 프로젝트별 영속 지식창고 경로."""
    return project_dir / "knowledge" / "store.json"


@dataclass
class KnowledgeStore:
    chunks: list[str] = field(default_factory=list)
    _vectors: list[list[float]] = field(default_factory=list)

    def add(self, chunks: list[str]) -> None:
        if not chunks:
            return
        vectors = embed_texts(chunks)
        self.chunks.extend(chunks)
        self._vectors.extend(vectors)

    def query(self, text: str, top_k: int = 5) -> list[str]:
        return [chunk for chunk, _score in self.query_with_scores(text, top_k)]

    def query_with_scores(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """청크와 코사인 유사도를 함께 반환한다.

        점수를 노출하는 이유: 검색된 청크 텍스트만으로는 호출자가 "이 소스가
        질문과 실제로 얼마나 관련 있는지" 판단할 방법이 없다 — 생성 전 커버리지
        점검(draft_cmd.py의 --min-coverage)이 이 점수를 근거로 판단한다.
        """
        if not self.chunks:
            return []
        import numpy as np  # lazy import — [rag] extra

        query_vec = np.array(embed_text(text))
        matrix = np.array(self._vectors)
        # 코사인 유사도 = 내적 / (노름의 곱). 0벡터 방지용 아주 작은 epsilon.
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec) + 1e-10
        scores = matrix @ query_vec / norms
        top_indices = np.argsort(-scores)[:top_k]
        return [(self.chunks[i], float(scores[i])) for i in top_indices]

    def __len__(self) -> int:
        return len(self.chunks)

    def save(self, path: Path) -> None:
        """청크+벡터를 JSON으로 저장한다. 임베딩을 다시 계산할 필요가 없어 재사용이 빠르다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"chunks": self.chunks, "vectors": self._vectors}, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "KnowledgeStore":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(chunks=data.get("chunks", []), _vectors=data.get("vectors", []))

    def merge(self, other: "KnowledgeStore") -> None:
        """다른 스토어의 청크+벡터를 이어붙인다(임베딩 재계산 없음) — draft가 새
        소스를 추가할 때마다 기존 저장된 스토어를 덮어쓰지 않고 누적하기 위함."""
        self.chunks.extend(other.chunks)
        self._vectors.extend(other._vectors)
