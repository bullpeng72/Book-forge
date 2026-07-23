# CLAUDE.md — Book-forge

## 프로젝트 개요

**Book-forge**는 AI 협업 다권 도서 저술 파이프라인이다. 주제 입력 → 기획안/목차(저자
승인 루프) → 마크다운 집필(직접 또는 RAG 보조) → HTML/PDF/발표자료 산출까지 한 파이프라인으로
묶고, 전 과정을 [agent-evaluator](https://pypi.org/project/agent-evaluator/) Gate A-G로
계측·게이팅한다.

- **자매 프로젝트**: Agent-Evaluator(`Media/Book`, `Media/AOO` — 하드코딩된
  `ORDERED_FILES` 방식 도서 빌드 스크립트의 이관 대상), Lecture_forge(에이전트
  구조·LLM Provider 팩토리 패턴의 설계 참고 대상, 코드 재사용은 하지 않음 — 완전
  독립 구현)
- **LLM Provider 기본값**: Ollama(로컬, API 키 불필요) — `create_llm()`이
  `LLM_PROVIDER` 미설정 시 `"ollama"`로 폴백한다.
- **버전**: 0.1.0 | Python 3.11+ | License: MIT

---

## Common Commands

```bash
# 설치
pip install -e ".[dev]"              # 코어 + pytest/ruff
pip install -e ".[dev,pdf,serve,rag]" # 전체 기능(Playwright/Flask/RAG) 포함 개발 설치
playwright install chromium           # [pdf] 설치 후 1회

# CLI
book-forge init                                    # LLM Provider(Ollama/OpenAI/Anthropic) 설정
book-forge new "<제목>" --constraints "..."         # 기획→목차 대화형 루프 + 스캐폴드
book-forge build html <slug>                        # 단일 HTML
book-forge build pdf <slug> [--chapter N]            # 챕터별 PDF (Playwright)
book-forge build slides <slug> [--chapter N] [--without-notes]  # Reveal.js 발표자료
book-forge edit <slug> [--port] [--no-browser]       # 웹 에디터
book-forge gate <slug> [--min-gate-score X] [--tcr X] [--baseline-version TAG] [--fail-on-regression PCT] [--junit-xml PATH]
book-forge draft <slug> <ch_no> --source a.pdf --source ./src [--top-k N] [--min-coverage F] [--yes] [--force]  # RAG 초안/레퍼런스 표 (옵션)
book-forge chat <slug> [--top-k N]                  # 지식창고 대화형 질의 (옵션)

# 마이그레이션 (Book/AOO → Book-forge 프로젝트)
python scripts/migrate_legacy_book.py --source <Book|AOO 디렉토리> --build-module build_book --target-slug <slug>

# 품질
pytest                        # 130개 테스트
ruff check src tests scripts
python -m build --wheel       # 패키징 검증 — editor/templates/*.html 포함 여부 반드시 확인
```

**사용자 데이터 위치**: `~/Documents/BookForge/`
```
~/Documents/BookForge/
├── .env
└── projects/<slug>/
    ├── 00_기획안.md   01_목차.md
    ├── Part_X_.../Chapter_XX_....md (+ images/)
    ├── outputs/ (html · pdf/ · *_slides.html)
    ├── knowledge/store.json ([rag] extra, draft가 쌓고 chat이 재사용)
    └── eval_results/ (*.json, *.html)
```

---

## 아키텍처

### 레이어 구조

```
agents/     LLM 호출 — 전부 @agent_eval 또는 @tool_guard 직접 적용 (Adapter 클래스 없음)
knowledge/  RAG — 소스 어댑터(PDF/코드저장소/텍스트) + Ollama 임베딩 인메모리 검색,
            영속화(save/load) 지원 ([rag] extra)
publish/    마크다운 → HTML/PDF/Slides — Book/AOO 엔진을 BookConfig 기반으로 일반화 이식
editor/     Flask 웹 에디터 — Part/Chapter MD 트리 직접 편집(완성 HTML 섹션 편집 아님)
eval/       PerformanceMonitor 팩토리
llm/        create_llm() — Ollama/OpenAI/Anthropic 통합 인터페이스, provider별 lazy import
cli/        Click 진입점 — 각 서브커맨드가 위 레이어를 조합
```

### 핵심 설계 결정과 그 근거

1. **Adapter 클래스 없이 `@agent_eval` 직접 사용**: Lecture_forge는 에이전트가 Pydantic
   모델을 반환해서 `@agent_eval`을 못 쓰고 Adapter로 감쌌다. Book-forge는 에이전트
   산출물이 처음부터 마크다운 문자열이라 `(str, EvalMetadata)` 반환 계약과 자연히
   맞는다 — `agents/planner.py`, `toc_designer.py`, `slide_condenser.py`,
   `chapter_drafter.py` 참고.

2. **`conversation_eval`을 쓰지 않는 이유(중요, 재검토 시 반드시 재확인)**: 저자
   리뷰 루프(`agents/review_loop.py`)는 다회 대화라 `conversation_eval`이 자연스러워
   보이지만, 실제 소스(`agent_evaluator/decorators.py`의
   `_CONVERSATION_EVAL_UNUSED_HARNESS_PARAMS`)를 확인한 결과 **30개 Harness Config
   전부가 시그니처로만 받고 평가에 반영되지 않는다**(SPEC-039 REQ-5, Non-Goal — 조용히
   무시되던 것을 `UserWarning`으로만 알림). `LoopDetectionConfig`가 실제로 저자 피드백
   반복을 잡아내려면, 라운드마다 `task_id_fn=lambda args, kwargs: f"review_{kwargs['kind']}_r{kwargs['round_no']}"`로
   독립된 `@agent_eval` 호출을 쓰는 수밖에 없다. 호출부는 반드시 키워드 인자로
   `revise(current_md=..., feedback=..., round_no=..., kind=...)` 형태로 불러야
   `task_id_fn`이 `kwargs`에서 값을 얻는다.

3. **`ScopeConfig`는 파일 경로가 아니라 도구 이름 allow/forbid다**: `ScaffoldAgent`가
   "프로젝트 디렉토리 밖 쓰기 금지"를 구현할 때 `ScopeConfig`를 쓸 수 없다
   (`agent_evaluator/gates/gate_b_behavioral/configs.py`의 `allowed_tools`/
   `forbidden_tools` 필드 확인 완료). 경로 포함 검사는 `agents/scaffold.py`,
   `editor/server.py`의 이미지 서빙 라우트가 직접 구현한다(resolved path가
   `project_dir.resolve()`의 하위인지 확인) — Harness Config가 대신해주지 않는다.

4. **팀 동시성은 opt-in**: `TeamConcurrencyConfig`(`editor/server.py`의 저장 경로)는
   `.aoo/claims.jsonl`에 활성 클레임이 있을 때만 충돌을 감지한다. 새 클레임 관리
   CLI를 만들지 않고 agent-evaluator에 이미 있는 `agent-eval claims add/list/release/audit`를
   그대로 재사용하는 게 의도된 설계다 — Book-forge 쪽에 claims 관리 기능을 추가하지 말 것.

5. **`book-forge gate`는 새 판정 로직이 아니라 서브프로세스 위임**:
   `sys.executable -m agent_evaluator.cli.main gate ...`로 호출한다. 콘솔 스크립트
   이름(`agent-eval`)에 의존하지 않는 이유는 pipx 등에서 의존성의 entry point가
   PATH에 노출되지 않을 수 있어서다 — `agent-eval`이라는 문자열로 subprocess를
   부르는 코드를 추가하지 말 것.

6. **RAG는 벡터 DB 없이 numpy 인메모리**: `knowledge/store.py`의 `KnowledgeStore`는
   ChromaDB 등을 쓰지 않는다 — 챕터 한 편 분량 소스에는 별도 벡터 DB 프로세스가
   과한 인프라라는 판단. 임베딩은 항상 Ollama(`/api/embeddings`)만 지원 — chat LLM
   provider가 OpenAI/Anthropic이어도 RAG 임베딩은 로컬 Ollama를 쓴다(provider별
   임베딩 API 통합은 미구현, 필요해지면 `knowledge/embeddings.py`를 확장).

7. **`plan --revise`의 챕터 재조정은 chapter_no를 안정 식별자로 취급한다**:
   `agents/scaffold.py`의 `reconcile_chapters()` — 새 목차의 각 챕터 경로에 이미
   파일이 있으면 절대 건드리지 않고(저자 집필 보존), 같은 chapter_no의 옛 챕터가
   존재하는데 제목이 바뀌어 경로만 달라졌다면 파일을 **재생성이 아니라 이동**시켜
   내용을 보존한다(images/도 함께 이동). 새 목차에서 완전히 빠진 chapter_no는
   **삭제하지 않고** orphaned로만 보고한다 — 저자가 챕터 순서 자체를 재배열하는
   경우(예: 3번을 1번으로 옮김)는 다른 챕터로 오인해 이상하게 매칭될 수 있다
   (알려진 한계, 실사용에서 문제되면 안정 UUID 도입 검토). 실측 검증: 저자 집필
   내용이 있는 챕터는 실제로 보존됐고, 제목이 바뀐 챕터는 실제로 내용 손실 없이
   이동함을 실제 Ollama 세션으로 확인 완료.

8. **일반 능력 A–F(RAG 확장)는 "AI Agent 강의를 만들려면 무엇이 필요한가" 분석에서
   도출된 일반 아키텍처다** — 특정 주제 전용 기능이 아니다. C(근거 검증)·D(실증
   게이트)·F(대안 제안)는 사실상 하나의 파이프라인(생성 전 커버리지 점검 → 낮으면
   F 트리거 → 그래도 진행하면 생성 → 생성 후 Gate 점수 노출)이고, D는 C에 새 판정
   로직을 추가한 게 아니라 `content_type in {"exercise","diagram"}`일 때 임계값만
   더 엄격하게 적용한다(`draft_cmd.py`의 `_STRICT_CONTENT_TYPES`). 이 결합 방식을
   바꿀 때는 `draft_cmd.py` 하나만 보면 된다 — 로직이 여러 파일에 흩어져 있지 않다.

   **실측으로 발견한 두 가지 상호작용 버그(설계상 감안하고 갈 것)**:
   - *커버리지 점검은 새 `--source`가 아니라 프로젝트 전체 지식창고를 대상으로
     한다*: E(영속화)가 있는 한 이건 사이드이펙트가 아니라 구조적 결과다 — 새로
     추가한 소스가 무관해도 기존에 쌓인 소스가 그럴듯하게 검색되면 낮은 커버리지
     경고가 안 뜬다(재현: 무관한 일기 텍스트를 추가했는데 기존 코드 소스 때문에
     평균 유사도 0.77로 임계값 0.5를 통과함).
   - *RAG 소스 누출*: `--source`로 넣은 코드 저장소에 프롬프트 템플릿 문자열이
     있으면(예: `agents/prompts.py`), LLM이 그 형식(`ALT:`, `TITLE:/BULLET:/NOTES:`,
     ` ```toc ` 블록)을 본문에 그대로 흉내 내거나 이어 붙이는 걸 실제로 확인했다.
     Book-forge 자신의 소스 디렉토리를 RAG 소스로 쓸 때 특히 잘 발생한다(자기
     참조 특성상 원천적으로 없애기 어려움) — 후처리 필터는 아직 없음.

   **임베딩 컨텍스트 길이(실측 버그, 수정 완료)**: `mxbai-embed-large`는 청크가
   길면 500 에러("the input length exceeds the context length")를 낸다 — 코드
   저장소 청크 기본 크기를 1200→500자로 낮췄고, `knowledge/embeddings.py`의
   `embed_text()`가 그 특정 오류에 한해 텍스트를 절반으로 잘라 1회만 재시도한다
   (`_retry=False`로 무한 재귀 방지). 이 재시도 로직을 건드릴 때는 재귀 종료
   조건을 반드시 유지할 것.

### `agent_eval` 실제 반환값 계약 (실측 확인됨)

`@agent_eval`로 감싼 함수가 `(response, EvalMetadata(...))` 튜플을 반환해도, **호출자는
`response`만 받는다** — `EvalMetadata`는 데코레이터가 벗겨내고 계측에만 쓴다
(`decorators.py`의 `caller_result, _ = _split_raw(raw); return caller_result` 확인
완료). `agents/*.py`의 모든 `build_*()` 팩토리 함수가 반환하는 호출 가능 객체는 항상
`str`을 반환한다 — 호출부에서 튜플 언패킹을 시도하지 말 것.

### 목차 매니페스트(````toc` 블록) 형식

`01_목차.md`는 사람이 읽는 마크다운 목차 + 기계가 파싱하는 ` ```toc ` 코드 블록을
함께 담는다. 각 줄: `파트번호|파트제목|챕터번호|챕터제목` (파이프 구분, 챕터번호는
책 전체 기준 순차 증가). `book_forge.models.parse_toc_manifest()`가 파싱하고,
`ChapterSpec.part_dir_name`/`chapter_file_name`이 실제 파일 경로를 계산한다
(`slugify()` — 한글은 유지, 구두점만 언더스코어로 정리). 이 형식을 바꾸면
`toc_designer.py`의 `TOC_PROMPT`, `models.parse_toc_manifest()`,
`scripts/migrate_legacy_book.py`의 `build_toc_manifest()` 세 곳을 함께 고쳐야 한다.

### 프로젝트 제목 저장 규약 (실제로 한 번 깨졌던 지점)

`00_기획안.md`는 **첫 줄이 항상 `# <책 제목>` H1**이어야 한다. `PlannerAgent`의
산출물 자체는 `## 목적`으로 바로 시작하므로(제목이 없음), `cli/commands/new_cmd.py`가
저장 시점에 `f"# {title}\n\n{proposal_md}"`로 명시적으로 title을 붙인다.
`cli/project_utils.py`의 `load_title()`은 "첫 비어있지 않은 줄"이 아니라 **H1만**
찾도록 되어 있다(과거 "## 목적"을 제목으로 잘못 집어 `outputs/목적.html`이 생성된
실제 버그의 수정 결과 — `tests/test_project_utils.py`에 회귀 테스트 있음). 이 두 곳
중 하나만 고치면 다시 깨진다.

---

## 알려진 한계 (재작업 전 확인)

| 항목 | 내용 |
|---|---|
| PDF의 Mermaid | `startOnLoad` 대기 후 인쇄하는 단순화된 경로 — Book/AOO 원본의 SVG 청크 캡처 미이식. 매우 큰 다이어그램은 페이지 경계에서 잘릴 수 있음 |
| CDN 의존 | Mermaid.js/highlight.js/Reveal.js는 CDN — LLM 호출은 Ollama로 오프라인 가능하지만 **PDF 빌드는 Playwright가 CDN을 실제 로드해야 해서 네트워크 필요** |
| 팀 동시성 | `agent-eval claims add`를 아무도 안 쓰면 검사가 항상 통과(설계상 opt-in) |
| RAG 임베딩 | Ollama 전용, chat LLM provider와 무관 |
| RAG 출력 안정성 | 로컬 모델이 가끔 ` ```markdown ` 코드펜스로 전체 응답을 감싸는 등 프롬프트를 완벽히 안 지킬 수 있음 — 초안은 사람이 항상 검토 |
| RAG 소스 누출 | 코드 저장소 소스에 프롬프트 템플릿이 있으면 그 형식이 본문에 섞여 나올 수 있음(실측 확인) |
| 커버리지 사전 점검 범위 | 새 `--source`가 아니라 프로젝트 전체 지식창고 기준(E와 C의 구조적 결합 결과) |
| `scaffold` 독립 실행, `home`의 일부 플랫폼 검증 | 미구현/부분 검증 |

---

## 마이그레이션 스크립트 관련 참고

`scripts/migrate_legacy_book.py`는 Book/AOO의 `build_book.py`/`build_aoo_book.py`를
**동적 import**해서 `ORDERED_FILES`/`MERMAID_INJECTIONS`만 읽는다(`if __name__ ==
"__main__":` 가드로 보호돼 있어 import해도 실제 빌드가 실행되지 않음 — 확인 완료).
`MERMAID_INJECTIONS`는 앵커 헤딩 텍스트가 정확히 일치할 때만 자동 인라인화하고,
불일치 항목은 자동 반영하지 않은 채 콘솔에 목록만 보고한다 — 이 부분을 "더 똑똑하게"
자동 매칭하려는 시도(퍼지 매칭 등)는 원본 실행 결과(Media/Book 34챕터 이관 시
9/15 인젝션 키가 매칭 실패)로 보아 신중해야 한다: 실패한 키들은 대부분 앵커가
"##"이 아니라 다른 구조이거나 챕터가 아닌 대상(README, 부록)이었다.

---

## 테스트 작성 규칙 (이 프로젝트에서 확립된 패턴)

- **LLM을 실제로 호출하는 테스트는 만들지 않는다** — `FakeLLM`(`.generate()`만
  구현한 간단한 클래스)을 주입해 오프라인·결정론적으로 테스트한다
  (`tests/test_slide_builder.py`, `tests/test_chapter_drafter.py` 참고).
- **agent-evaluator 실제 객체는 목(mock)하지 않는다** — `PerformanceMonitor`,
  `LiveGuardrail`, `TeamConcurrencyConfig` 등은 실제 인스턴스를 만들어 검증한다
  (`tests/test_editor_server.py`의 팀 동시성 409 테스트, `tests/test_gate_cmd.py`의
  실제 서브프로세스 호출 테스트 참고) — 이 SDK와의 통합이 프로젝트의 핵심 가치이므로
  목으로 가리면 실제 배선 오류를 못 잡는다.
- **패키징 변경 후에는 반드시 `python -m build --wheel` + 새 venv에 설치해 회귀
  테스트한다** — editable install만으로는 `package-data` 누락을 못 잡는다
  (`editor/templates/index.html` 실제 누락 사고 확인·수정 완료).
