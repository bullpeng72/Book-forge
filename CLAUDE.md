# CLAUDE.md — Book-forge

## 프로젝트 개요

Book-forge는 주제(또는 코드 저장소) → 기획안/목차(저자 승인 루프) → 마크다운 챕터
집필 → HTML/PDF/EPUB/발표자료로 이어지는 다권 도서 저술 파이프라인이다. 전 과정을
[agent-evaluator](https://pypi.org/project/agent-evaluator/) SDK의 Harness Gate
A–G로 계측한다 — Book-forge 자신은 품질 판정 로직을 만들지 않고, agent-evaluator가
이미 제공하는 계측·게이팅 기능을 가져다 쓰는 **응용 프로그램**이다.

- **Version:** 0.1.0 | **Python:** 3.11+ | **License:** MIT | **Author:** Sungwoo Kim
- **핵심 의존성:** `agent-evaluator>=0.9.9`(필수), `click`/`pydantic`/`markdown`/`requests`/`python-dotenv`(코어),
  `playwright`(PDF/EPUB, `[pdf]`), `pypdf`+`numpy`(RAG, `[rag]`), `flask`(웹 에디터, `[serve]`)
- **기본 LLM Provider:** Ollama(로컬, API 키 불필요) — `LLM_PROVIDER` 환경변수로 OpenAI/Anthropic 전환 가능
- **테스트:** 409개, `pytest`(`.venv/bin/python -m pytest`로 실행 — 시스템 Python이 아니라 프로젝트 자체 venv 사용)

---

## 명령어

```bash
# 개발 환경
pip install -e ".[dev,pdf,serve,rag]"
playwright install chromium      # PDF/EPUB 빌드용 (실제로는 EPUB은 zipfile만 써서 불필요, PDF만 필요)

# 품질 검사 (커밋 전 항상 실행)
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests scripts
python -m build --wheel          # 패키징 검증 — editor/templates/*.html 포함 여부 반드시 확인

# CLI 개발 중 실행 (venv 스크립트 직접 호출)
./.venv/bin/book-forge new "제목" --source ./some_repo
./.venv/bin/book-forge gate <slug> --min-gate-score 0.0
```

**주의**: `pip install -e .`가 시스템/conda 환경(`Evaluator` 등)에 이미 잡혀 있을 수 있으므로,
셸 세션의 `python`/`pytest`가 조용히 다른 환경을 가리킬 수 있다 — 항상 `./.venv/bin/python -m pytest`처럼
프로젝트 venv를 명시적으로 지정한다(실측으로 이 문제에 걸린 적 있음: 시스템 conda 환경에는
`book_forge` 패키지가 없어 `ModuleNotFoundError`가 47개 테스트 파일에서 동시에 발생했었다).

---

## 주요 기능 → 소스 위치

| 기능 | 핵심 파일 | 비고 |
|---|---|---|
| 기획/목차 대화형 루프 | `agents/planner.py`, `agents/toc_designer.py`, `agents/review_loop.py`, `cli/commands/new_cmd.py` | `PlannerAgent`/`TOCDesignerAgent` + 라운드별 개별 `@agent_eval`(`conversation_eval` 미사용, 아래 참고) |
| 챕터 스캐폴딩 | `agents/scaffold.py` | `@tool_guard` — 파일 쓰기는 사후 채점이 아니라 실행 전 차단 대상 |
| 구조적 코드 인덱싱 | `knowledge/code_index.py` | `ast` 정적 분석, 표준 라이브러리만 사용(새 의존성 없음), Python 전용 |
| RAG 소스 어댑터 | `knowledge/sources.py`, `knowledge/pdf_source.py`, `knowledge/web_search.py` | PDF/코드 저장소/텍스트/URL 자동 판별 |
| RAG 지식창고 | `knowledge/store.py`, `knowledge/embeddings.py` | numpy 인메모리 코사인 유사도(벡터 DB 의도적 미사용) + Ollama 임베딩 |
| 챕터 초안(narrative/exercise) | `agents/chapter_drafter.py` | `rag_mode=True` |
| 레퍼런스 표/다이어그램/캡스톤/모듈 레퍼런스 | `agents/reference_table.py`, `agents/diagram_generator.py`, `agents/capstone_generator.py`, `agents/module_reference.py` | `content_type`별 전용 생성기 |
| 저커버리지 대안 제안 | `agents/alternative_suggester.py` | 자동 차단 대신 대안 제시 + 저자 승인 |
| 생성 후 정적 검증 | `agents/demonstration_verifier.py`, `agents/code_consistency_checker.py`, `agents/sdk_version_pin.py`, `agents/code_example_verifier.py`, `agents/term_consistency_checker.py` | 전부 LLM 미호출, Gate 점수와 무관한 별도 축 |
| 지식창고 Q&A | `agents/chat_agent.py`, `cli/commands/chat_cmd.py` | `ConversationSession`으로 대화 이력 유지 |
| 다관점 리뷰 패널 | `agents/review_panel.py`, `cli/commands/review_cmd.py` | 감독자-작업자 패턴, Book-forge에서 Gate F(다중 에이전트)가 실제 값을 얻는 유일한 지점 |
| 리서치 에이전트 | `agents/research_agent.py`, `knowledge/web_search.py`, `cli/commands/research_cmd.py` | 검색 쿼리 생성 → DuckDuckGo 검색 → 저자 선택 |
| HTML/PDF/EPUB/발표자료 빌드 | `publish/html_builder.py`, `publish/pdf_builder.py`, `publish/epub_builder.py`, `publish/slide_builder.py` | 공용 `publish/markdown_engine.py` |
| 표지/찾아보기 | `publish/front_matter.py`, `publish/book_index.py` | `--author` 등 front matter, `--with-index` 찾아보기 |
| 웹 에디터 | `editor/server.py` | Flask, 저장 시 `LiveGuardrail(team_concurrency=...)` 경유 |
| 품질 게이팅 | `cli/commands/gate_cmd.py` | `PerformanceMonitor.merge()`로 책 전체 집계 후 `agent-eval gate` 위임 |
| 용어 일관성 검사 | `agents/term_consistency_checker.py`, `cli/commands/lint_cmd.py` | 챕터 간 백틱 기술 용어 표기 불일치 발견·보고 |
| 목차 개정 이력 | `models.py`(`append_toc_revision_entries`), `agents/review_loop.py`의 `on_feedback` 콜백 | 새 LLM 호출 없이 순수 문자열 조작 |

---

## 프로세스 — 파이프라인 아키텍처

### 전체 흐름

```
사용자 입력(주제, --source)
        │
        ▼
PlannerAgent.propose_plan()  ──(승인 루프)──▶  00_기획안.md
        │
        ▼  (code_structure: --source가 코드 저장소면 code_index.py 결과를 여기서 주입)
TOCDesignerAgent.design_toc()  ──(승인 루프)──▶  01_목차.md (사람이 읽는 부분 + ```toc 매니페스트)
        │
        ▼
ScaffoldAgent.scaffold_project()  (@tool_guard, LiveGuardrail 세션)
        │                                        ──▶  Part_X_.../Chapter_XX_....md (빈 스텁)
        ▼
[--source가 있으면 곧바로 배치 초안으로 진행, 없으면 여기서 종료]
        │
        ▼
ChapterDrafterAgent / ReferenceTableAgent / DiagramGeneratorAgent / CapstoneGeneratorAgent
  / ModuleReferenceAgent  (content_type별 분기, draft_cmd.py가 라우팅)
        │
        ▼  (생성 직후 정적 검증 — LLM 미호출)
demonstration_verifier / code_consistency_checker / sdk_version_pin / code_example_verifier
        │
        ▼
publish/*_builder.py  ──▶  outputs/(html · pdf/ · epub · slides)
        │
        ▼
gate_cmd.py  ──▶  PerformanceMonitor.merge(eval_results/*.json)  ──▶  agent-eval gate 위임
```

### 데코레이터 배선 패턴 (모든 LLM 에이전트 공통)

에이전트 모듈은 전부 **팩토리 함수**를 노출한다 — `build_propose_plan(llm, monitor)`처럼
호출해야 `@agent_eval`이 실제로 적용된 함수를 얻는다. `monitor`가 프로젝트(책)마다 새로
생성되므로(각자 다른 `eval_results/` 경로), 모듈 import 시점에 고정 데코레이션할 수 없다.

```python
def build_propose_plan(llm: LLM, monitor: PerformanceMonitor) -> ProposePlanFn:
    @agent_eval(monitor, task_type="planning", question_arg="topic",
        goal_alignment=GoalAlignmentConfig(ignore_no_tool_tasks=False),
        instructions=InstructionConfig(fail_on_violation=False),
        explainability=ExplainabilityConfig(min_reasoning_length=30))
    def propose_plan(topic: str, constraints: str, ground_truth: str = "") -> tuple[str, EvalMetadata]:
        prompt = PLAN_PROMPT.format(topic=topic, constraints=constraints or "없음")
        return llm.generate(prompt, system=PLAN_SYSTEM_PROMPT), EvalMetadata(...)
    return propose_plan
```

**왜 `conversation_eval`이 아니라 라운드별 `@agent_eval`인가** (`review_loop.py`): 실제
agent-evaluator 소스(`decorators.py`의 `_CONVERSATION_EVAL_UNUSED_HARNESS_PARAMS`)를
확인한 결과, `conversation_eval`은 31개 Harness Config 전부를 시그니처로만 받고 평가에
반영하지 않는다(설계상 Non-Goal). 저자 리뷰 루프에서 `LoopDetectionConfig`가 실제로
작동하려면 각 라운드를 독립된 TaskResult로 기록해야 하므로, `task_id_fn=lambda args,
kwargs: f"review_{kwargs['kind']}_r{kwargs['round_no']}"`로 라운드별 개별 `@agent_eval`
호출 방식을 쓴다 — 호출부는 반드시 키워드 인자로 불러야 `task_id_fn`이 동작한다.

### 부작용이 있는 동작은 다른 축이다

파일 쓰기처럼 부작용이 있는 함수(`scaffold.py`, `editor/server.py`)는 `@agent_eval`이
아니라 `@tool_guard` + `live_guardrail_session()`을 쓴다 — 자세한 내용은
[Agent-Evaluator와의 관계](#agent-evaluator와의-관계) 참고.

---

## 입력/출력 데이터 형식

### 목차 매니페스트 (`01_목차.md`)

사람이 읽는 마크다운(제목/소개)과, 코드가 파싱하는 ` ```toc ` 코드 펜스 블록을 한 문서
안에 함께 담는다.

```
## Part 1. 기초
- Chapter 1. 서론
- Chapter 2. 환경 설정

```toc
1|기초|1|서론|narrative
1|기초|2|환경 설정|exercise
```
```

파이프(`|`)로 구분된 5개 필드: `part_no|part_title|chapter_no|chapter_title|content_type`.
`content_type` 생략 시 `narrative` 기본값(`models.py::parse_toc_manifest()`). 이 코드
블록만 `load_toc()`가 파싱하므로, 그 위에 붙는 다른 섹션(예: `## 개정 이력`)은 빌드
파이프라인에 영향을 주지 않는다.

### 프로젝트 디렉토리 (`~/Documents/BookForge/projects/<slug>/`)

```
<slug>/
├── 00_기획안.md
├── 01_목차.md
├── front_matter.json      # --author 등 지정 시(publish/front_matter.py), 전부 빈 값이면 파일 자체 없음
├── sdk_versions.json       # --check-package 최초 사용 시 대상 SDK 버전 고정
├── Part_X_.../Chapter_XX_....md (+ images/)
├── knowledge/store.json    # KnowledgeStore — chunks + vectors, save/load/merge
├── eval_results/           # PerformanceMonitor가 저장하는 *.json(+*.html) — 챕터별 개별 파일
│   └── _merged_gate_result.json  # gate_cmd.py가 만드는 병합 산출물(다음 집계에서 자동 제외)
└── outputs/ (html · pdf/ · epub · *_slides.html)
```

`eval_results/`는 챕터마다 별도 `PerformanceMonitor`가 개별 저장한다(`draft_ch{NN}.json`
등) — `book-forge gate`가 `--file` 없이 호출되면 이 전부를
`PerformanceMonitor.merge()`로 합쳐 책 전체를 판정한다(파일이 1개뿐이면 병합 없이
그대로 사용, 완전한 하위 호환).

### `KnowledgeStore` 청크 태그

`knowledge/sources.py`가 청크 앞에 `"# 파일: <경로>"` 또는 `"# 출처: <URL>"` 태그를 붙인다
— `query_with_scores(..., max_per_source=N)`이 이 태그로 한 소스가 검색 결과를 독점하는
것을 막고, `_cited_url_sources()`가 이 태그로 실제 인용된 URL만 챕터 말미
`## 참고 자료`에 자동으로 붙인다. 청킹 후 매 조각에 태그를 다시 붙이므로(`_tag_each_chunk()`),
여러 청크로 쪼개지는 큰 파일도 태그가 첫 조각에만 남지 않는다.

---

## Agent-Evaluator와의 관계

Book-forge의 모든 에이전트는 agent-evaluator SDK를 **직접** import해서 쓴다(별도
어댑터 계층 없음 — 산출물이 처음부터 `(str, EvalMetadata)` 반환 계약과 자연히 맞기
때문). 아래는 에이전트별 실제 배선이다.

| 에이전트 | 데코레이터 | 핵심 Harness Config | 채점 축 |
|---|---|---|---|
| `PlannerAgent` | `@agent_eval` | `GoalAlignmentConfig`, `InstructionConfig`, `ExplainabilityConfig` | Gate A |
| `TOCDesignerAgent` | `@agent_eval` | `PlanConfig`, `SubtaskConfig`, `ContextRetentionConfig` | Gate A |
| `AuthorReviewLoop`(`review_loop.py`) | `@agent_eval`(라운드별) | `LoopDetectionConfig` | Gate B |
| `ScaffoldAgent` | `@tool_guard` | `LoopDetectionConfig`(LiveGuardrail) | 실시간(배치 Gate 아님) |
| `SlideCondenserAgent` | `@agent_eval` | `InstructionConfig`, `ExplainabilityConfig`, `SLAConfig` | Gate A/D |
| `ChapterDrafterAgent`, `ReferenceTableAgent` | `@agent_eval(rag_mode=True)` | `HallucinationDetector`(자동 활성화), `SLAConfig`, `ThreatSeverityConfig` | Gate C/D/E |
| `AlternativeSuggesterAgent` | `@agent_eval` | `InstructionConfig`, `ExplainabilityConfig` | Gate A |
| `ChatAgent` | `@agent_eval(rag_mode=True)` | `HallucinationDetector`(자동 활성화), `SLAConfig` | Gate C/D |
| `ReviewerAgent`/`ChiefEditorAgent`(`review_panel.py`) | `@agent_eval` | `AgentRoleConfig`, `ConflictResolutionConfig` | Gate F |

**배치 평가(사후 채점) vs 실시간 가드레일(실행 전 차단)** — 이 둘은 완전히 다른 축이다:

- **배치**: 결과(응답 문자열)를 반환하는 함수는 `@agent_eval`로 감싸 세션이 끝난 뒤
  Gate A–G로 채점한다.
- **실시간**: 파일 쓰기 등 부작용이 있는 함수(`scaffold.py::write_chapter_stub`,
  `editor/server.py::_write_chapter_file`)는 `@tool_guard` + `live_guardrail_session()`
  으로 감싸 **실행 전에** 차단한다. `LiveGuardrail`이 자동으로 막아주는 것은
  `LoopDetectionConfig` 기반 반복 탐지와 `TeamConcurrencyConfig` 기반 저장 충돌뿐이다 —
  "프로젝트 디렉토리 밖 쓰기 금지" 같은 경로 검사는 SDK가 대신 해주지 않으므로
  애플리케이션이 직접 구현했다(`ScopeConfig`는 파일 경로가 아니라 도구 이름 목록이라
  용도가 다르다).

**책 전체 게이팅**: `gate_cmd.py`는 새 판정 로직을 만들지 않고 agent-evaluator에 이미
있던 `PerformanceMonitor.load_from_file()`/`.merge()`를 처음 실제 연결했다. 병합
산출물(`_merged_gate_result.json`)은 다음 집계 대상에서 제외해 피드백 루프를 막는다.

**Gate 가중치 커스터마이징**: `eval/monitor.py::build_book_monitor()`가 `.env`의
`BOOK_FORGE_GATE_A_TCR_WEIGHT`/`_C_TCR_WEIGHT`/`_B_LOOP_WEIGHT`를 읽어
`PerformanceMonitor`에 전달한다(agent-evaluator 기본값: `gate_a_tcr_weight=0.4`,
`gate_c_tcr_weight=0.4`, `gate_b_loop_weight=0.0`). 파싱 실패는 조용히 무시(관대한 파싱
원칙, 오타 하나가 파이프라인을 죽이지 않게).

**LLM Judge는 Ollama를 지원하지 않는다**: agent-evaluator의 `LLMJudge`는 OpenAI/Anthropic
전용이다 — `--enable-llm-judge`(`new`/`draft` 옵트인)를 켜려면 기본 Provider(Ollama)와
무관하게 별도 API 키가 필요하다.

**보안 트래커는 상시 on**: `build_book_monitor()`가 `enable_security_metrics=True`로
생성한다(외부 RAG 소스 대비). `enable_hallucination_detection`은 별도 모니터 레벨
플래그로는 꺼두고, `rag_mode=True`를 쓰는 에이전트에서만 개별적으로 켜진다.

---

## 코딩 컨벤션

- **Formatter**: ruff, line-length=100, target-version py311
- **에이전트 모듈**: 전부 `build_X(llm, monitor) -> Fn` 팩토리 패턴 — 모듈 레벨에서
  데코레이션하지 않는다
- **정적 검증기**(`demonstration_verifier.py` 등): LLM 미호출, `@agent_eval` 없음,
  실패해도 저장을 막지 않는 "참고용" 원칙 유지
- **관대한 파싱**: 저자 입력/LLM 출력 파싱은 형식을 어겨도 예외를 던지지 않고 안전한
  폴백으로 처리한다(`_parse_reviewer_output()`, `_gate_weight_overrides()` 등 — 오타
  하나가 전체 파이프라인을 죽이면 안 된다는 원칙)
- **경로 안전성**: 부작용이 있는 파일 쓰기 함수는 `resolved_project not in
  resolved_target.parents` 패턴으로 프로젝트 디렉토리 밖 쓰기를 직접 방어한다(SDK가
  대신 해주지 않음)

---

## 테스트 작성 시 주의할 점

**import 바인딩 함정**(이미 두 번 걸림): `from X import get_data_dir`로 가져와 호출하는
코드를 테스트할 때, `monkeypatch.setattr()`는 **그 함수가 정의된 모듈**이 아니라 **그
함수를 import해서 실제로 호출하는 모듈**의 네임스페이스를 패치해야 한다. `from X import Y`는
import 시점의 스냅샷 바인딩이라, `X.Y`를 나중에 패치해도 이미 `Y`를 자기 네임스페이스로
가져온 다른 모듈에는 반영되지 않는다.

```python
# 틀림 — resolve_project_dir()이 정의된 project_utils.py 자신이 get_data_dir을
# import해서 쓰므로, config_module을 패치해도 반영 안 됨
monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)

# 맞음 — 실제로 get_data_dir()을 호출하는 모듈(project_utils)을 패치
monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
```

**venv 확인**: 테스트는 반드시 `./.venv/bin/python -m pytest`로 실행한다(위 [명령어](#명령어)
참고) — 시스템/conda 환경에는 `book_forge`가 설치돼 있지 않을 수 있다.

**의도한 이유로 통과/실패하는 테스트 쌍을 만든다**: 정규식에 `re.MULTILINE`을 빠뜨린
버그가, "항목 없음 → `passed=True`" 폴백 때문에 첫 번째(통과) 테스트에서는 드러나지 않고
두 번째(의도적으로 실패해야 하는) 테스트에서만 잡힌 사례가 있었다 — 새 검증 로직을 짤 때는
항상 "이게 왜 통과하는가"뿐 아니라 "이게 왜 실패해야 하는가"도 테스트해야 한다.

---

## 설계 결정 배경 (자주 나오는 질문)

- **RAG는 벡터 DB가 아니라 numpy 인메모리다**(`knowledge/store.py`): 챕터 한 편의 집필
  보조에 필요한 소스 규모(PDF 몇 개~수십 개 청크)에는 ChromaDB 같은 별도 벡터 DB가 과한
  인프라라는 의도적 선택 — 별도 프로세스·스키마 없이 JSON 파일 하나로 저장/로드한다.
  규모가 커지면 재검토 대상(현재는 실측으로 확인된 병목 없음).
- **Ollama 추론 모델은 `think: false`로 강제한다**(`llm/provider.py::OllamaLLM`):
  `qwen3.6:35b-mlx` 같은 추론 모델이 `num_predict` 예산을 사고 과정에 다 써버리면
  최종 응답이 빈 문자열로 저장되는 실제 버그를 재현해 고쳤다.
  `think: false`를 페이로드에 항상 포함해 사고 과정 없이 바로 답하게 강제한다 —
  추론을 지원 안 하는 모델은 이 옵션을 무시한다(에러 없음).
  이 버그를 놓치면 아무 에러 없이 챕터 파일이 통째로 빈 채 저장되므로, `OllamaLLM` 관련
  코드를 고칠 때는 이 계약을 깨지 않도록 주의한다.
- **자기검토·자동 재작성 루프는 없다**: 정적 검증기와 Gate C 경고는 결과를 **보고**할
  뿐, 그 결과를 근거로 LLM이 스스로 다시 쓰게 만드는 경로가 없다. `review_loop.py`가
  이 능력에 가장 가깝지만 사람이 피드백을 입력해야 돈다 — 자동화하려면
  `LoopDetectionConfig`/`MAX_REVIEW_ROUNDS` 같은 안전장치를 사람 개입 없는 루프에도
  똑같이(더 엄격하게) 적용해야 한다.
- **이미지 자동 배치는 없다**: 저자가 마크다운에 `![alt](./images/xxx.png)`를 직접
  삽입해야 한다. 범위가 크고 Book-forge의 핵심 가치(코드/구조 분석 기반 저술)와 거리가
  있어 우선순위를 낮게 뒀다.
- **팀 동시성은 클라이언트 opt-in이다**(`TeamConcurrencyConfig`): 저자가 `agent-eval
  claims add`로 스코프를 실제로 선점한 경우에만 충돌을 감지한다 — 서버가 강제하는 락이
  아니다. 팀 전체가 이 관례를 지켜야 실효성이 있다.

---

## 파일 구조

```
src/book_forge/
├── agents/         # LLM 호출 에이전트(13개) + 정적 검증기(5개) — 전부 팩토리 함수 패턴
├── knowledge/      # RAG — 소스 어댑터, 임베딩, 지식창고, 구조적 코드 인덱싱
├── publish/        # 마크다운 → HTML/PDF/EPUB/Slides
├── editor/         # Flask 웹 에디터
├── eval/           # PerformanceMonitor 팩토리(build_book_monitor)
├── llm/            # create_llm() — Ollama/OpenAI/Anthropic 통합 인터페이스
├── cli/commands/   # Click 명령 — 각 명령이 위 레이어를 조합
└── models.py       # ChapterSpec, parse_toc_manifest, append_toc_revision_entries
```

프로젝트 전반의 진행 상황·완료된 개선 항목 이력은 `SPEC.md`에 별도로 기록한다(이
파일은 아키텍처·컨벤션 참고용, 항목별 이력은 다루지 않는다).
