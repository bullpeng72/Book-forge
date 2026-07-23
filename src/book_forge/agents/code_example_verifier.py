"""코드 예제 실행 검증 — 챕터의 python 코드 블록을 실제로 실행해 통과하는지
확인한다(9개 후보 기능의 1번, CodeExampleAgent — C(근거 검증 계층)의 세 번째
검증기 종류).

`demonstration_verifier.verify_exercise_code()`는 `ast.parse()`로 **문법**만
본다 — "실제로 실행하면 성공하는가"는 지금까지 한 번도 확인하지 않았다(이
프로젝트가 그 결정을 CLAUDE.md에 명시적으로 기록해뒀다: "LLM이 생성한 임의
코드를 자동으로 실행하지는 않는다"). 이 모듈이 그 결정을 뒤집는 게 아니라,
**별도의 명시적 옵트인 계층**으로 실행 검증을 추가한다 — 기존 exercise/
diagram/reference_table/capstone 검증은 전부 그대로 문법·구조 검증만 하고,
`--execute-examples`를 명시적으로 켰을 때만 이 모듈이 개입한다.

안전장치:
  - **In-process `exec()`가 아니라 `subprocess`로 격리 실행한다** — 프로세스
    크래시가 CLI 자체를 죽이지 않고, 부모 프로세스의 메모리(예: API 키가 담긴
    환경 변수)에 직접 접근하지 못한다.
  - **타임아웃(기본 10초)** — 무한루프/행 코드가 CLI를 영원히 막지 않는다.
  - **`sys.executable`로 현재 venv를 그대로 재사용** — target_package가 이미
    설치된 환경에서 실행되므로 별도 설치 스텝이 필요 없다(단, 파일시스템/
    네트워크 접근은 OS 수준으로 격리되지 않는다 — 컨테이너 없는 순수 Python
    subprocess의 한계, README "알려진 한계"에 명시).
  - **실패해도 초안 저장을 막지 않는다** — 다른 D/C 검증(exercise 문법,
    code_consistency)과 같은 "경고만, 저장은 유지" 원칙을 그대로 따른다.

로컬 코드베이스 대상(일반 능력 I): 분석 대상이 pip install된 패키지가 아니라
로컬 디렉토리면, 생성된 예제 코드의 `from <local_pkg> import X`가 기본
subprocess 환경에서는 ImportError가 난다(현재 venv의 site-packages에는 없는
모듈이므로). `extra_pythonpath`를 주면 그 경로(및 부모 경로 — target_dir
자신이 패키지인지, target_dir 안에 낱개 모듈이 있는지 미리 알 수 없어 둘 다
추가하는 휴리스틱)를 subprocess의 `PYTHONPATH`에 넣어 로컬 import가 풀리게
한다.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from book_forge.agents.demonstration_verifier import VerificationResult

_CODE_FENCE_RE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

DEFAULT_TIMEOUT_SECONDS = 10.0


def _build_execution_env(extra_pythonpath: Optional[Path]) -> Optional[dict[str, str]]:
    if extra_pythonpath is None:
        return None
    # 절대 경로로 정규화해야 한다 — subprocess의 cwd는 임시 디렉토리(tmp_dir)라
    # 상대 경로를 그대로 PYTHONPATH에 넣으면 엉뚱한 위치를 가리킨다(실측으로
    # 발견한 버그: 상대 경로를 넣었더니 ModuleNotFoundError가 계속 재현됨).
    resolved = extra_pythonpath.resolve()
    existing = os.environ.get("PYTHONPATH", "")
    candidates = [str(resolved), str(resolved.parent)]
    new_pythonpath = os.pathsep.join(candidates + ([existing] if existing else []))
    return {**os.environ, "PYTHONPATH": new_pythonpath}


def verify_code_execution(
    draft_md: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    extra_pythonpath: Optional[Path] = None,
) -> VerificationResult:
    """```python 코드 블록마다 별도 subprocess로 실행해 exit code 0인지 확인한다.

    코드 블록이 하나도 없으면 "확인할 코드가 없음"으로 통과 처리한다(exercise
    문법 검증과 달리, narrative 챕터는 코드가 없는 게 정상이라 실패로 보지
    않는다 — content_type별 필수 여부는 draft_cmd.py가 호출 시점에서 이미
    판단했다).

    extra_pythonpath를 주면(로컬 코드베이스 대상, 일반 능력 I) 그 경로와
    부모 경로를 subprocess의 PYTHONPATH에 추가해, 설치 안 된 로컬 패키지의
    import가 풀리게 한다.
    """
    blocks = _CODE_FENCE_RE.findall(draft_md)
    if not blocks:
        return VerificationResult(
            content_type="code_execution",
            passed=True,
            detail="실행할 python 코드 블록이 없습니다.",
        )

    env = _build_execution_env(extra_pythonpath)
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="book_forge_code_example_") as tmp_dir:
        for i, block in enumerate(blocks, 1):
            snippet_path = Path(tmp_dir) / f"snippet_{i}.py"
            snippet_path.write_text(block, encoding="utf-8")
            try:
                result = subprocess.run(
                    [sys.executable, str(snippet_path)],
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                issues.append(f"코드 블록 {i}: 실행 시간이 {timeout:.0f}초를 초과했습니다.")
                continue
            if result.returncode != 0:
                error_line = (result.stderr or "").strip().splitlines()[-1:] or ["(오류 메시지 없음)"]
                issues.append(f"코드 블록 {i}: 실행 실패 (exit {result.returncode}) — {error_line[0]}")

    passed = not issues
    detail = (
        f"코드 블록 {len(blocks)}개 실행 검증 통과"
        if passed
        else f"코드 블록 {len(blocks)}개 중 {len(issues)}개 실행 실패"
    )
    return VerificationResult(
        content_type="code_execution", passed=passed, detail=detail, issues=issues
    )
