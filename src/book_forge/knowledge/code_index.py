"""구조적 코드 인덱싱 — 코드 저장소를 텍스트 청크로만 쪼개지 않고, Python
표준 라이브러리 `ast`로 정적 분석해 모듈/클래스/함수 인벤토리 + 내부/외부
의존 관계를 뽑아낸다 (일반 능력 H: 구조적 코드 인덱싱).

`knowledge/sources.py`의 `load_code_repo_source()`는 파일을 텍스트로 읽어
청크·임베딩할 뿐이다 — "이 프로젝트에 어떤 모듈이 있는가", "A가 B를 어떻게
의존하는가" 같은 **파일 간 구조적 관계**는 청크 유사도 검색으로 잘 안 잡힌다
(import문이 청크 경계에서 잘리거나, 애초에 그래프 구조가 텍스트 나열에는
없음). 이 모듈은 청크 검색을 대체하는 게 아니라 보강한다 — 정적 분석으로
뽑은 구조 요약을 별도 텍스트로 만들어 같은 `KnowledgeStore`에 추가 청크로
넣으면, "구조를 설명하라" 유형의 질문에도 검색으로 근거를 찾을 수 있다.

Python(`.py`)만 지원한다 — `ast`가 표준 라이브러리라 새 의존성이 필요 없다는
게 이유다(tree-sitter 등 다국어 파서는 추가하지 않는다, 의존성 최소화 원칙).
다른 언어 파일은 이 인덱서를 그냥 건너뛰고, 기존 `load_code_repo_source()`의
청크 검색 경로로만 커버된다(자연스러운 축소, 별도 처리 불필요).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ClassSummary:
    name: str
    bases: list[str]
    docstring: Optional[str]
    methods: list[str]


@dataclass
class FunctionSummary:
    name: str
    args: list[str]
    docstring: Optional[str]


@dataclass
class ModuleSummary:
    path: str  # 인덱싱 루트 기준 상대 경로
    imports: list[str] = field(default_factory=list)
    classes: list[ClassSummary] = field(default_factory=list)
    functions: list[FunctionSummary] = field(default_factory=list)


def _first_line(docstring: Optional[str]) -> Optional[str]:
    if not docstring:
        return None
    stripped = docstring.strip()
    return stripped.splitlines()[0].strip() if stripped else None


def _extract_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _extract_classes(tree: ast.Module) -> list[ClassSummary]:
    classes: list[ClassSummary] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        try:
            bases = [ast.unparse(b) for b in node.bases]
        except (ValueError, RecursionError):
            bases = []
        methods = [
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ]
        classes.append(
            ClassSummary(
                name=node.name,
                bases=bases,
                docstring=_first_line(ast.get_docstring(node)),
                methods=methods,
            )
        )
    return classes


def _extract_functions(tree: ast.Module) -> list[FunctionSummary]:
    functions: list[FunctionSummary] = []
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        ):
            args = [a.arg for a in node.args.args]
            functions.append(
                FunctionSummary(
                    name=node.name, args=args, docstring=_first_line(ast.get_docstring(node))
                )
            )
    return functions


def extract_module_summary(rel_path: str, source_text: str) -> Optional[ModuleSummary]:
    """단일 .py 파일 내용을 파싱해 ModuleSummary를 만든다.

    문법 오류(예: 다른 언어 파일에 .py 확장자가 잘못 붙었거나, 저장소에
    의도적으로 깨진 파일이 있는 경우)가 있으면 예외를 던지지 않고 None을
    반환한다 — 저장소 전체 인덱싱이 파일 하나 때문에 중단되지 않게 한다.
    """
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return None
    return ModuleSummary(
        path=rel_path,
        imports=_extract_imports(tree),
        classes=_extract_classes(tree),
        functions=_extract_functions(tree),
    )


def build_structure_index(directory: Path, *, max_files: int = 200) -> list[ModuleSummary]:
    """디렉토리를 재귀 탐색해 .py 파일마다 ModuleSummary를 만든다.

    load_code_repo_source()와 같은 제외 규칙(__pycache__/.git)을 쓴다 —
    두 인덱싱 경로가 같은 파일 집합을 봐야 "구조 요약에는 있는데 청크
    검색에는 없는" 불일치가 생기지 않는다.
    """
    files = sorted(
        p
        for p in directory.rglob("*.py")
        if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts
    )[:max_files]

    summaries: list[ModuleSummary] = []
    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        summary = extract_module_summary(str(fpath.relative_to(directory)), content)
        if summary is not None:
            summaries.append(summary)
    return summaries


def internal_import_roots(directory: Path) -> set[str]:
    """이 디렉토리를 패키지 루트로 삼는 import의 첫 세그먼트 후보를 모은다.

    예: directory가 src/book_forge면 "book_forge" 자신 + 바로 아래
    서브디렉토리 이름(agents/knowledge/cli 등)이 후보다 — 대부분의 파이썬
    프로젝트에서 `from book_forge.agents.x import y`처럼 루트 패키지
    이름으로 절대 import하는 관례를 그대로 이용한 휴리스틱이다. 완벽한
    import 해석기가 아니다(상대 import나 sys.path 조작까지는 못 따라간다) —
    "정확한 그래프"가 아니라 "내부/외부를 대략 구분하는 근거"가 목적이다.

    `code_consistency_checker.py`의 로컬 코드베이스 대상 검증(일반 능력 I)도
    이 함수를 그대로 재사용한다 — "본문이 언급한 import가 분석 대상 프로젝트
    소속인가"를 판단하는 기준이 여기서 쓰는 것과 같은 문제이기 때문이다.
    """
    roots = {directory.name}
    try:
        roots.update(
            child.name
            for child in directory.iterdir()
            if child.is_dir() and not child.name.startswith((".", "__"))
        )
    except OSError:
        pass
    return roots


def format_structure_summary(summaries: list[ModuleSummary], directory: Path) -> str:
    """ModuleSummary 목록을 사람/LLM이 읽기 좋은 구조 요약 텍스트로 렌더링한다.

    KnowledgeStore에 그대로 청크·임베딩되므로, 검색됐을 때 "이건 정적 분석
    결과다"라는 걸 알 수 있게 헤더를 남긴다(청크 태그 관례 — load_code_repo_source()가
    "# 파일: xxx.py"를 남기는 것과 같은 이유).
    """
    if not summaries:
        return ""

    internal_roots = internal_import_roots(directory)
    lines = [f"# 프로젝트 구조 요약 (정적 분석, {len(summaries)}개 모듈)"]

    for s in summaries:
        lines.append(f"\n## {s.path}")
        if s.imports:
            internal = sorted({i for i in s.imports if i.split(".")[0] in internal_roots})
            external = sorted({i for i in s.imports if i.split(".")[0] not in internal_roots})
            if internal:
                lines.append(f"- 내부 의존: {', '.join(internal)}")
            if external:
                lines.append(f"- 외부 의존: {', '.join(external)}")
        for c in s.classes:
            base_str = f"({', '.join(c.bases)})" if c.bases else ""
            doc_str = f" — {c.docstring}" if c.docstring else ""
            method_str = f" [{', '.join(c.methods)}]" if c.methods else ""
            lines.append(f"- 클래스 `{c.name}{base_str}`{doc_str}{method_str}")
        for fn in s.functions:
            args_str = ", ".join(fn.args)
            doc_str = f" — {fn.docstring}" if fn.docstring else ""
            lines.append(f"- 함수 `{fn.name}({args_str})`{doc_str}")

    return "\n".join(lines)
