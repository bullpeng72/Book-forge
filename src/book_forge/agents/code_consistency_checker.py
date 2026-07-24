"""코드-본문 정합성 검사 — 챕터 본문이 언급한 심볼이 실제 설치된 패키지에
존재하는지 검증한다(9개 후보 기능의 6번, C(근거 검증 계층)의 새 검증기 종류).

`demonstration_verifier.verify_exercise_code()`는 코드 블록의 "문법"만
확인한다 — `from agent_evaluator import ScopeConfig`가 문법적으로 완벽해도
ScopeConfig가 실제로 그 이름으로 존재하는지, `ScopeConfig.path`처럼 존재하지
않는 필드를 언급했는지는 검증하지 않는다. 이 세션 초반 "ScopeConfig는 경로가
아니라 도구 이름 기반"이라는 걸 소스 코드로 직접 확인 안 했으면 잘못된 설계를
그대로 밀어붙일 뻔했던 것과 같은 종류의 오류를, 이 모듈이 생성 직후 자동으로
잡는다.

content_type과 무관하게 동작한다(narrative 챕터도 프로즈 중에 클래스/설정
이름을 언급하므로) — demonstration_verifier.py의 content_type 분기와는 별개
축이라, draft_cmd.py가 --check-package가 주어졌을 때만 별도로 호출한다.

로컬 코드베이스 대상 검증(일반 능력 I): `--check-package`에 설치된 패키지명
대신 **로컬 디렉토리 경로**를 주면(`Path(target).is_dir()`) `verify_code_consistency()`가
자동으로 로컬 모드로 전환한다 — "개념 설명 + 특정 프로젝트 소스코드 분석"형
강의는 분석 대상이 pip install된 패키지가 아니라 그냥 클론해온 로컬 저장소인
경우가 많은데, 기존 방식(`importlib.import_module()`)은 이런 경우 항상
ImportError를 낸다. 로컬 모드는 `importlib` 대신 `knowledge/code_index.py`의
정적 분석(구조적 코드 인덱싱, 일반 능력 H)으로 심볼 존재를 대조한다 — H가
이미 검증한 인프라를 그대로 재사용하는 것이라 새 파싱 로직을 만들지 않는다.
"""
from __future__ import annotations

import builtins
import dataclasses
import importlib
import pkgutil
import re
import typing
from pathlib import Path

from book_forge.agents.demonstration_verifier import VerificationResult

_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.+)$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)\s*$", re.MULTILINE)
_BACKTICK_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`")
# 대문자로 시작 + 소문자 포함(길이 4자 이상) — URL/PDF/API 같은 두문자어를 걸러내는
# 최소 휴리스틱. 완벽하지 않지만 오탐(엉뚱한 걸 위반으로 보고)보다는 누락(검증
# 대상에서 조용히 제외)을 택한다.
_CAMEL_CASE_RE = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)*$")
# None/True/False, ValueError 같은 표준 예외, Optional/List 같은 typing 이름은
# "본문이 언급했지만 target_package 소속이 아닌" 정상적인 Python 어휘다 — 실측
# 확인: "음수인 경우 None으로 보정됩니다" 같은 문장에서 `None`이 오탐으로
# 잡혔었다(target_package에 없다고 보고했지만 애초에 target_package 소속이라고
# 주장한 적 없는 문장이었음).
_BUILTIN_EXCLUSIONS = frozenset(
    name for name in (set(dir(builtins)) | set(dir(typing))) if name[:1].isupper()
)


def _split_import_names(names_part: str) -> list[str]:
    """``X, Y as Z, (A, B)`` 형태에서 실제로 import되는 이름만 뽑는다(별칭은 원래 이름)."""
    cleaned = names_part.strip().strip("()")
    names = []
    for part in cleaned.split(","):
        part = part.strip()
        if not part:
            continue
        name = part.split(" as ")[0].strip()
        if name and name != "*":
            names.append(name)
    return names


def _extract_imports(text: str) -> list[tuple[str, list[str]]]:
    """(모듈 경로, [이름들]) 쌍 목록. ``import X``는 이름 없이 모듈 자체만 확인한다."""
    imports: list[tuple[str, list[str]]] = []
    for module, names_part in _FROM_IMPORT_RE.findall(text):
        imports.append((module, _split_import_names(names_part)))
    for names_part in _IMPORT_RE.findall(text):
        for module in _split_import_names(names_part):
            imports.append((module, []))
    return imports


def _looks_like_class_name(name: str) -> bool:
    base = name.split(".")[0]
    if base in _BUILTIN_EXCLUSIONS:
        return False
    return bool(_CAMEL_CASE_RE.match(base)) and len(base) >= 4


def _extract_backtick_symbols(text: str) -> list[str]:
    seen: list[str] = []
    for name in _BACKTICK_RE.findall(text):
        if _looks_like_class_name(name) and name not in seen:
            seen.append(name)
    return seen


def _has_attr_or_field(obj, name: str) -> bool:
    """hasattr()만 쓰면 dataclasses.field(default_factory=...) 필드를 놓친다 —
    @dataclass는 default_factory 필드에 클래스 레벨 속성을 남기지 않는다(실측
    확인: ScopeConfig.allowed_tools가 hasattr()로는 False로 나옴). fields()도
    함께 확인해야 이런 필드를 올바르게 "존재함"으로 판정한다."""
    if hasattr(obj, name):
        return True
    if dataclasses.is_dataclass(obj):
        return any(f.name == name for f in dataclasses.fields(obj))
    return False


def _resolve_dotted(root_module, path: list[str]) -> bool:
    obj = root_module
    for attr in path:
        if not _has_attr_or_field(obj, attr):
            return False
        obj = getattr(obj, attr, None)
        if obj is None and attr != path[-1]:
            return False
    return True


# target_package별 서브모듈 심볼 테이블 캐시(Spec L) — walk_packages는 서브모듈을
# 전부 import하므로 챕터마다 반복하면 느리다. 최상위 __name__을 키로 캐시한다.
_package_symbol_cache: dict[str, set[str]] = {}


def _walk_package_symbols(root_module) -> set[str]:
    """target_package 산하 전체 서브모듈을 순회해 공개 멤버 이름을 평평하게 모은다(Spec L).

    ``importlib.import_module(target_package)``만으로는 최상위 네임스페이스에
    재노출된 이름만 보인다 — 실측 확인: `Settings`(agent_evaluator.config),
    `KoreanRAGDatasetGenerator`(agent_evaluator.datasets), `LiveGuardrail`
    (agent_evaluator.gates.live_guardrail)는 전부 실존하는 클래스인데 최상위
    재노출이 없어 `_resolve_dotted`가 매번 오탐(없음)으로 판정했다. 이 함수는
    로컬 모드(verify_code_consistency_local)가 이미 쓰는 "평평한 심볼 테이블"
    아이디어를 설치된 패키지 서브모듈 전체로 확장한 것 — 새 파싱 로직이 아니라
    같은 발상의 재사용이다.
    """
    name = getattr(root_module, "__name__", None)
    if name is not None and name in _package_symbol_cache:
        return _package_symbol_cache[name]

    symbols: set[str] = set(n for n in dir(root_module) if not n.startswith("_"))
    package_path = getattr(root_module, "__path__", None)
    if package_path is not None:
        prefix = root_module.__name__ + "."
        for _finder, module_name, _is_pkg in pkgutil.walk_packages(package_path, prefix):
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue  # 선택적 의존성 등으로 로드 실패한 서브모듈은 건너뛴다
            symbols.update(n for n in dir(module) if not n.startswith("_"))

    if name is not None:
        _package_symbol_cache[name] = symbols
    return symbols


def verify_code_consistency_local(draft_md: str, *, target_dir: Path) -> VerificationResult:
    """target_dir가 설치된 패키지가 아니라 로컬 디렉토리(pip install 안 한
    분석 대상 프로젝트 소스)일 때 쓰는 경로다(일반 능력 I).

    importlib 기반 경로처럼 "정확히 어느 서브모듈에 있는가"까지는 확인하지
    않는다 — 로컬 디렉토리의 상대 경로를 절대 dotted import 경로로 신뢰성
    있게 매핑할 방법이 없기 때문이다(target_dir가 패키지 루트인지, src/
    상위 디렉토리인지 알 수 없음). 대신 **평평한 심볼 테이블**(대상 디렉토리
    전체에서 발견한 클래스/함수 이름 전부)에 대해 "이 이름이 프로젝트 어딘가에
    실제로 존재하는가"만 확인한다 — H(구조적 코드 인덱싱)의
    internal_import_roots()로 "이 import가 분석 대상 프로젝트 소속으로 보이는가"만
    먼저 거르고, 소속으로 보이면 평평한 심볼 테이블과 대조한다.
    """
    from book_forge.knowledge.code_index import build_structure_index, internal_import_roots

    summaries = build_structure_index(target_dir)
    if not summaries:
        return VerificationResult(
            content_type="code_consistency",
            passed=False,
            detail=f"대조할 .py 모듈을 찾지 못했습니다: {target_dir}",
        )

    known_symbols: set[str] = set()
    for s in summaries:
        known_symbols.update(c.name for c in s.classes)
        known_symbols.update(fn.name for fn in s.functions)

    internal_roots = internal_import_roots(target_dir)
    issues: list[str] = []
    checked = 0

    for module_path, names in _extract_imports(draft_md):
        # 첫 세그먼트만이 아니라 임의 세그먼트로 대조한다 — target_dir가 실제
        # 패키지 루트(예: src/book_forge)가 아니라 그 서브디렉토리(예:
        # src/book_forge/agents)를 가리켜도(흔한 사용 패턴) internal_roots에는
        # "agents"만 들어있고 import는 "book_forge.agents.x"로 시작해 첫
        # 세그먼트 비교로는 못 잡는다(실측으로 확인한 실패 케이스). 대신
        # known_symbols 대조가 최종 필터라 오탐 위험은 낮다.
        if not (set(module_path.split(".")) & internal_roots):
            continue  # 이 프로젝트 소속으로 보이지 않는 import는 대조 대상이 아님
        checked += 1
        for name in names:
            if name not in known_symbols:
                issues.append(
                    f"본문의 `from {module_path} import {name}` — "
                    f"{target_dir}에서 {name}을(를) 찾지 못했습니다."
                )

    for symbol in _extract_backtick_symbols(draft_md):
        base = symbol.split(".")[0]
        checked += 1
        if base not in known_symbols:
            issues.append(f"본문이 언급한 `{symbol}` — {target_dir}에서 확인되지 않습니다.")

    if checked == 0:
        return VerificationResult(
            content_type="code_consistency",
            passed=True,
            detail=f"{target_dir} 관련 import/심볼 언급이 없어 대조할 항목이 없습니다.",
        )

    passed = not issues
    detail = (
        f"{checked}개 항목 모두 {target_dir}에서 확인됨"
        if passed
        else f"{checked}개 항목 중 {len(issues)}개가 {target_dir}에 없음"
    )
    return VerificationResult(
        content_type="code_consistency", passed=passed, detail=detail, issues=issues
    )


def verify_code_consistency(draft_md: str, *, target_package: str) -> VerificationResult:
    """본문이 언급한 import/심볼이 target_package에 실제로 존재하는지 검증한다.

    LLM을 호출하지 않고, target_package를 실제로 import해 대조한다
    (importlib.import_module — 저자가 CLI에서 명시적으로 지정한 패키지만
    로드한다, 임의 원격 코드 실행이 아니다).

    target_package가 실제 로컬 디렉토리 경로면(`Path(target_package).is_dir()`)
    설치된 패키지가 아니라 분석 대상 프로젝트 소스 자체로 간주해 로컬 모드
    (verify_code_consistency_local)로 자동 전환한다 — 일반 능력 I.
    """
    local_dir = Path(target_package)
    if local_dir.is_dir():
        return verify_code_consistency_local(draft_md, target_dir=local_dir)

    try:
        root_module = importlib.import_module(target_package)
    except ImportError as exc:
        return VerificationResult(
            content_type="code_consistency",
            passed=False,
            detail=f"대조 대상 패키지를 import할 수 없습니다: {target_package} ({exc})",
        )

    issues: list[str] = []
    checked = 0

    for module_path, names in _extract_imports(draft_md):
        if not (module_path == target_package or module_path.startswith(target_package + ".")):
            continue  # 표준 라이브러리 등 다른 패키지 import는 대조 대상이 아님
        checked += 1
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            issues.append(f"본문의 `import {module_path}` — 실제로 존재하지 않는 모듈입니다.")
            continue
        for name in names:
            if not _has_attr_or_field(module, name):
                issues.append(
                    f"본문의 `from {module_path} import {name}` — "
                    f"{module_path}에 {name}이(가) 없습니다."
                )

    for symbol in _extract_backtick_symbols(draft_md):
        checked += 1
        path = symbol.split(".")
        if _resolve_dotted(root_module, path):
            continue
        # 서브모듈 전체 재확인(Spec L)은 "최상위 클래스/함수 이름 자체"가
        # target_package 어딘가에 실존하는지만 본다 — `ScopeConfig.path`처럼
        # base(ScopeConfig)는 최상위에 있는데 딸린 필드가 없는 경우까지 이
        # 폴백으로 구제하면 진짜 오탐(존재하지 않는 필드)을 놓친다. base가
        # 애초에 최상위에서 안 보일 때만(재노출 누락 케이스) 폴백을 적용한다.
        if not _has_attr_or_field(root_module, path[0]) and path[0] in _walk_package_symbols(
            root_module
        ):
            continue
        issues.append(f"본문이 언급한 `{symbol}` — {target_package}에서 확인되지 않습니다.")

    if checked == 0:
        return VerificationResult(
            content_type="code_consistency",
            passed=True,
            detail=f"{target_package} 관련 import/심볼 언급이 없어 대조할 항목이 없습니다.",
        )

    passed = not issues
    detail = (
        f"{checked}개 항목 모두 {target_package}에서 확인됨"
        if passed
        else f"{checked}개 항목 중 {len(issues)}개가 {target_package}에 없음"
    )
    return VerificationResult(
        content_type="code_consistency", passed=passed, detail=detail, issues=issues
    )
