# 부록 D. 구조적 코드 인덱싱 상세 — `code_index.py` 전체

4장(§4.3)이 "AST 정적 분석으로 모듈/클래스/함수 목록을 뽑는다"고 요약한 기능의 실제 구현이다. 4장 본문에서는 이 부록으로 옮겨, 순차 파이프라인이라는 그 챕터의 원래 주제에 집중할 수 있게 했다 — `--source`로 코드 저장소를 분석하는 원리 자체가 궁금할 때 여기로 돌아오면 된다.

## D.1 한 파일을 어떤 형태로 요약하는가

```python
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
    path: str
    imports: list[str] = field(default_factory=list)
    classes: list[ClassSummary] = field(default_factory=list)
    functions: list[FunctionSummary] = field(default_factory=list)
```

파일 하나가 결국 "이름·상속 관계·독스트링 첫 줄·공개 메서드 목록을 가진 클래스들"과 "이름·인자·독스트링 첫 줄을 가진 함수들"의 목록으로 요약된다.

## D.2 실제로 뽑는 코드 — 표준 라이브러리 `ast`만 쓴다

```python
def _extract_classes(tree: ast.Module) -> list[ClassSummary]:
    classes: list[ClassSummary] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [ast.unparse(b) for b in node.bases]
        methods = [
            n.name for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ]
        classes.append(ClassSummary(
            name=node.name, bases=bases,
            docstring=_first_line(ast.get_docstring(node)), methods=methods,
        ))
    return classes


def extract_module_summary(rel_path: str, source_text: str) -> Optional[ModuleSummary]:
    """단일 .py 파일 내용을 파싱해 ModuleSummary를 만든다.

    문법 오류가 있으면 예외를 던지지 않고 None을 반환한다 — 저장소 전체
    인덱싱이 파일 하나 때문에 중단되지 않게 한다.
    """
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return None
    return ModuleSummary(
        path=rel_path, imports=_extract_imports(tree),
        classes=_extract_classes(tree), functions=_extract_functions(tree),
    )
```

`ast.parse(source_text)`가 이 기능의 핵심이다 — 파이썬 인터프리터가 코드를 실행하기 전에 만드는 것과 같은 구문 트리(AST)를 만든 뒤, `tree.body`를 순회하며 클래스·함수 정의만 골라낸다. **코드를 한 줄도 실행하지 않는다** — `import`문이 실행되지 않으므로 어떤 부작용도 없고, 문법만 유효하면 의존성이 하나도 설치되지 않은 저장소도 인덱싱할 수 있다. `except SyntaxError: return None`이 3장·10장에서 반복된 원칙과 같은 자리에 있다는 것도 눈여겨볼 만하다 — 파일 하나가 깨져 있어도(다른 언어 파일에 `.py` 확장자가 잘못 붙는 등) 저장소 전체 인덱싱이 죽지 않는다.

## D.3 범위를 의도적으로 좁힌 지점

`code_index.py` 모듈 docstring이 이 기능의 범위를 명확히 긋는다.

> "`ast`가 표준 라이브러리라 새 의존성이 필요 없다는 게 이유다(tree-sitter 등 다국어 파서는 추가하지 않는다)."

Python(`.py`) 파일만 지원하고, 다른 언어 파일은 이 인덱서를 건너뛰고 기존 텍스트 청킹(`knowledge/sources.py`)으로만 처리된다 — "모든 언어를 지원하는 완벽한 인덱서"가 아니라 "가장 흔한 경우(Python 저장소)를 새 의존성 없이 잘 처리하는 인덱서"를 택한 것이다.

---

- `src/book_forge/knowledge/code_index.py` — 전체(`build_structure_index()`, `format_structure_summary()` 포함)
- 4장(§4.3) — 이 코드가 파이프라인 어디에 끼어드는지, `design_toc()`가 그 결과를 어떻게 쓰는지
