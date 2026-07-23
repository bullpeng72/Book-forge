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
book-forge draft <slug> --all --source ./src  # 미집필 챕터 전부 일괄 생성 (배치 모드, F는 확인 대신 스킵+리포트)
book-forge new "<제목>" --source ./src         # 기획→목차→스캐폴딩 직후 전체 챕터 자동 배치 초안까지 한 번에
book-forge chat <slug> [--top-k N]                  # 지식창고 대화형 질의 (옵션)

# 마이그레이션 (Book/AOO → Book-forge 프로젝트)
python scripts/migrate_legacy_book.py --source <Book|AOO 디렉토리> --build-module build_book --target-slug <slug>

# 품질
pytest                        # 140개 테스트
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

9. **배치 모드(`draft --all`)는 F의 정책을 "확인"에서 "스킵+리포트"로 바꾼다,
   판정 로직 자체는 그대로다**: `draft_cmd.py`의 `_draft_one_chapter(...,
   batch_mode=...)` 하나가 단일/배치 두 경로를 다 처리한다 — 로직을 복제하지
   않았다. 배치 모드에서 커버리지가 낮으면 `AlternativeSuggesterAgent` 호출
   자체를 안 한다(LLM 비용 절감 + 사람이 없는 상태에서 확인 프롬프트가 의미
   없음). 챕터별 결과는 `eval_results/draft_ch{NN:02d}.json`으로 **개별 저장**한다
   — 하나의 monitor로 전체를 누적 저장하면 `book-forge gate`/`load_gate_scores()`가
   여러 챕터의 점수를 뭉뚱그려 평균 내버려 "이 챕터가 문제"라는 신호를 잃는다.
   실측 검증: 실제 Ollama로 8챕터 배치(2분 34초) 완주, `eval_results/`에
   `draft_ch01.json`~`draft_ch08.json` 8개 개별 파일 생성, 배치 요약에 챕터별
   Gate C 점수가 정확히 분리되어 표시됨(`book-forge gate`의 "최신 파일 자동
   선택"도 `draft_ch08.json`을 올바르게 집음).

   **테스트 격리 관련 실측 버그(수정 완료, 이유 알아둘 것)**: `chat`/`draft`/
   `new`/`plan` 명령은 전부 `load_config()`를 부르는데, 이건 `python-dotenv`의
   `load_dotenv()`를 써서 `os.environ`에 **직접** 대입한다 — `monkeypatch.setenv`와
   달리 테스트가 끝나도 자동으로 안 돌아간다. 실제 사용자 홈에
   `~/Documents/BookForge/.env`가 존재하는 머신에서 이 명령들을 감싼 CliRunner
   테스트를 돌리면(그 안의 `get_data_dir()`을 모킹 안 했다면) 실제 `.env` 값이
   `os.environ`에 새어나가 이후 실행되는 다른 테스트를 오염시킨다(실측: `test_llm_provider.py`가
   `OLLAMA_MODEL` 기본값 검증에서 실패). `tests/conftest.py`의 `_isolated_environ`
   autouse fixture가 매 테스트 전후로 `os.environ` 전체를 스냅샷·복원해 이 문제를
   원천 차단한다 — 이 fixture를 지우거나 우회하지 말 것.

10. **`get_data_dir()`은 모듈마다 별도로 바인딩돼 있다 — 테스트에서 하나만
    패치하면 안 된다(실측으로 두 번 걸림)**: `book_forge/config.py`가 원본을
    정의하고, `cli/project_utils.py`가 `from book_forge.config import
    get_data_dir`로 재import한다. `monkeypatch.setattr(project_utils,
    "get_data_dir", ...)`는 `project_utils.resolve_project_dir()`(draft/build/
    gate/edit/chat/home이 씀)에만 영향을 준다 — `new_cmd.py`는 `project_utils`를
    거치지 않고 `config.ensure_project_dir()`을 직접 호출하므로 **반드시
    `monkeypatch.setattr(book_forge.config, "get_data_dir", ...)`로 따로
    패치해야 한다**. 안 그러면 테스트가 실제 사용자의 `~/Documents/BookForge/`에
    실제로 파일을 쓴다 — 실측: 이 실수로 `~/Documents/BookForge/projects/`에
    테스트 프로젝트가 실제로 생성된 적 있음(정리 완료). 새 명령을 추가할 때
    `new_cmd.py`처럼 `project_utils`를 안 거치는 경로를 또 만들지 않는 게
    최선이지만, 만들게 되면 이 노트를 기억할 것.

11. **`new --source`는 `draft --all`과 완전히 같은 배치 로직을 재사용한다,
    복제하지 않는다**: `draft_cmd.py`의 `collect_sources_into_store()`/
    `run_batch_draft()`/`_is_draftable()`/`_print_batch_summary()`를
    `new_cmd.py`가 그대로 import해서 스캐폴딩 직후에 호출한다. 저커버리지
    정책도 배치 모드와 동일(스킵+리포트, 확인 프롬프트 없음) — `new`는 이미
    기획/목차 리뷰 루프로 사람이 붙어있었으니, 이어지는 배치 단계까지 매
    챕터 확인을 요구하면 "자동으로 진행"이라는 요청의 취지가 없어진다는
    판단. 실측 검증: 실제 Ollama로 "주제 입력 → 기획 승인 → 목차 승인 →
    스캐폴딩 → 4챕터 배치 초안"이 한 명령·76초로 완주함을 확인.

12. **RAG 소스에 URL 지원을 추가할 때 무거운 파싱 라이브러리를 쓰지 않았다**:
    `knowledge/sources.py`의 `load_url_source()`는 이미 코어 의존성인
    `requests`로 GET 한 번 하고, 표준 라이브러리 `html.parser`
    (`_HTMLTextExtractor`)로 `<script>/<style>/<head>`만 걸러낸 나머지 텍스트를
    모은다 — trafilatura/readability 등 본문 추출 전용 라이브러리를 추가하지
    않는다(PDF는 pypdf, 코드/텍스트는 stdlib만 쓰는 기존 원칙과 동일선상).
    `load_source(source)`가 `_URL_RE`(`^https?://`)로 URL을 먼저 판별하고,
    아니면 기존처럼 `Path(source)` 기반 디렉토리/PDF/텍스트 판별로 폴백한다 —
    이 순서를 바꾸지 말 것(URL 문자열을 `Path()`로 잘못 해석하면 안 됨).
    `load_source()`는 `str`과 `Path`를 둘 다 받는다(`str(source)`로 먼저
    정규화) — 기존 호출부가 `Path` 객체를 넘기던 관행과 새 URL 문자열 호출을
    동시에 지원해야 했기 때문. CLI 쪽은 `draft_cmd.py`의 `_SourcePath`
    (`click.ParamType`)가 `http(s)://` 접두어면 그대로 통과시키고, 아니면
    `click.Path(exists=True)`로 위임한다 — `new_cmd.py`도 이 타입을 그대로
    import해서 쓴다(--source 검증 로직을 두 곳에 복제하지 않음). 알려진 한계:
    SPA처럼 JS로 렌더링되는 페이지는 텍스트를 거의 못 가져오고, robots.txt를
    존중하지 않으며, 재귀적으로 링크를 따라가지 않고 지정한 URL 1개만 가져온다
    (README "알려진 한계" 참고).

13. **D(실증 가능성 게이트) 강화는 "생성 전 임계값"에 "생성 후 정적 검증"을
    더한 것이다, 기존 pre-check를 대체하지 않는다**: 원래 설계 문서(일반 능력
    C 정의)는 "생성 후: 콘텐츠 유형에 맞는 검증기 실행 — code 스니펫은 실제
    실행/import 검증, reference_table은 소스 값과 표 값 대조"까지 요구했는데,
    실제 구현은 `_STRICT_CONTENT_TYPES`로 커버리지 임계값만 엄격하게 적용하는
    사전 점검에 그쳤다(생성된 결과물이 실제로 검증 가능한 형태인지는 한 번도
    확인 안 함). `agents/demonstration_verifier.py`가 그 생성 후 검증을
    채운다:
    - `exercise` → ```python 블록을 `ast.parse()`로 문법 검증. **LLM이 생성한
      임의 코드를 자동으로 실행하지는 않는다** — 부작용 없는 안전한 근사만
      확인하고, 실제 실행은 저자 몫으로 남긴다(원 설계의 "실제 실행" 요구를
      의도적으로 축소한 지점 — 재검토 시 착각하지 말 것).
    - `diagram` → ```mermaid 블록이 알려진 다이어그램 타입(`graph`/
      `flowchart`/`sequenceDiagram` 등)으로 시작하고 본문이 비어있지 않은지
      최소 구조만 확인(mermaid 파서를 새로 짜지 않음).
    - `reference_table` → 표 셀 값이 RAG 발췌문(`sources_text`)에 그대로
      등장하는 비율을 계산(기본 임계값 50%) — 소스에 없는 값을 표로 날조하는
      것을 잡아낸다.
    - `exercise`/`diagram` content_type은 지금까지 `chapter_drafter.py`의
      일반 서술형 프롬프트(`DRAFT_PROMPT`)로 생성됐다 — 검증 대상(코드/mermaid
      블록)이 애초에 안정적으로 생성된다는 보장이 없었다. `build_draft_chapter()`에
      `content_type` 파라미터(기본값 `"narrative"`, 하위 호환)를 추가해
      `DRAFT_PROMPT_EXERCISE`(`agents/prompts.py`)로 분기하고, 코드 블록을
      명시적으로 요구한다(diagram도 처음엔 여기서 `DRAFT_PROMPT_DIAGRAM`으로
      같이 처리했지만, 항목 14에서 독립 에이전트로 다시 옮겼다 — 지금은
      `DRAFT_PROMPT_DIAGRAM`이 존재하지 않는다).
    - 검증 결과는 **agent-evaluator의 Gate 점수를 바꾸지 않는다** — SDK 내부
      판정 로직에 손대지 않고, Book-forge 자체 신호로 CLI(`🔬 실증 가능성
      검증: ✅/⚠️`)와 배치 요약에만 노출한다. 기존 Gate C/D 노출과 같은 철학
      — **실패해도 초안 저장/빌드를 막지 않는다**(참고용, `book-forge gate`가
      최종 판정). 원 설계는 D 실패를 F(대안 제안)로 넘기는 흐름까지 그렸지만,
      검증이 생성 *후*에 일어나 F가 트리거되는 생성 *전* 흐름과 시점이 달라
      재구조화가 필요했다 — 이번엔 정보 노출까지만 구현하고 F 연동은 하지
      않았다(향후 필요해지면 재검토).

14. **DiagramGeneratorAgent는 diagram content_type을 chapter_drafter.py에서
    분리해 reference_table.py와 같은 "독립 에이전트" 패턴으로 승격한 것이다,
    새 판정/검증 로직이 아니다**: 9개 후보 기능(AI Agent 강의 분석에서 도출)의
    7번 항목이 원래 요구한 것도 이 형태였다 — "일반 서술형 프롬프트에 다이어그램
    요구사항만 얹기"가 아니라 표(B의 reference_table.py)처럼 독립된 생성기.
    직전 커밋(D 강화)에서는 diagram을 `chapter_drafter.py`의 `content_type`
    분기(`DRAFT_PROMPT_DIAGRAM`)로 임시로 처리했었는데, 이번에 그 분기를
    제거하고 `agents/diagram_generator.py`(`build_generate_diagram()`)로
    이전했다 — 프롬프트/계측 배선은 그대로(`rag_mode=True`, `SLAConfig`,
    `ThreatSeverityConfig` 동일), `draft_cmd.py`의 `_draft_one_chapter()`가
    `content_type == "diagram"`이면 이 모듈을 호출하도록 분기만 추가했다
    (`reference_table` 분기 바로 다음 `elif`). `chapter_drafter.py`는 이제
    diagram을 모르는 content_type으로 취급해 기본 `DRAFT_PROMPT`로 안전하게
    폴백한다(직접 호출돼도 예외 없음, `test_chapter_drafter.py`로 확인).
    `agents/demonstration_verifier.py`(D)는 이 에이전트가 만든 결과물을 그대로
    검증한다 — 검증 로직 자체는 이전 커밋에서 이미 완성돼 있었으므로 손대지
    않았다. `exercise`는 아직 독립 에이전트로 승격하지 않았다(요청 범위 밖 —
    9개 후보 기능 중 별개 항목인 "실습/캡스톤 스캐폴드"와 헷갈리지 말 것,
    지금 `exercise`는 여전히 `chapter_drafter.py`의 content_type 분기로 처리됨).

15. **ReviewPanelAgent(`agents/review_panel.py`)는 Book-forge에서 처음으로 진짜
    감독자-작업자(supervisor-worker) 멀티에이전트 협업을 구현한 것이다 —
    이전까지 6개 에이전트가 전부 순차 파이프라인이라 `book-forge gate`의 Gate
    F(Multi-Agent Coordination)는 항상 N/A였다("일반 능력 G"로 명명, A–F와는
    다른 축 — RAG 집필 보조가 아니라 "강의가 가르치는 개념을 도구 자신이
    실제로 실행해봐야 한다"는 요구에서 나옴)**:
    - 정확성/가독성 검토자(worker) 2명이 같은 챕터를 독립 검토 → 편집장
      (ChiefEditorAgent, supervisor)이 종합해 최종 판정. `book-forge review
      <slug> <chapter_no>` CLI로 실행한다(`run_review_panel()`을 감싸는 얇은
      래퍼, `cli/commands/review_cmd.py`).
    - **consensus는 자유 텍스트 어휘 유사도가 아니라 구조화 신호로 계산한다**:
      `eval_consensus(agent_interactions=[{"agent": role_name, "intent":
      verdict}, ...])`(SPEC-009 REQ-1) — 리뷰어들이 서로 다른 어휘로 같은
      결론에 도달해도 "불일치"로 오판되지 않는다. `agent_evaluator.decorators`
      내부에는 `consensus_responses`라는 배치 전용 내부 파라미터가 있어
      `agent_eval(consensus=...)`를 단일 호출에 써도 항상 조용히 건너뛰어지는데
      (SDK 자체 경고 메시지가 이 워크어라운드를 안내함), 그 워크어라운드가
      `eval_consensus()`를 `agent_evaluator.helpers.taskresult_helpers`에서
      직접 import해 수동 호출한 뒤 `EvalMetadata(extra={"consensus": {...}})`로
      편집장의 `@agent_eval` 호출에 주입하는 것이다 — `review_panel.py`가
      정확히 이 패턴을 쓴다. 재검토 시: `agent_eval(consensus=ConsensusConfig())`
      데코레이터 파라미터에 기대지 말 것 — 단일 호출에서는 무조건 무시된다.
    - **coordination_score는 `monitor.agent_coordination_tracker.track_interaction()`
      을 리뷰어마다 위임(delegation)·응답(communication) 2회씩 명시적으로 호출해야
      채워진다** — `@agent_eval`이 자동으로 기록해주지 않는다(트래커가 별도
      객체이기 때문).
    - **agent_role은 각 리뷰어의 담당 관점을 `AgentRoleConfig.allowed_action_keywords`
      (이 관점이면 언급했을 근거 단어)/`forbidden_action_keywords`(다른 관점
      침범 시 쓰였을 단어)로 검사한다** — tool_calls가 없는(순수 텍스트 리뷰)
      상황이라 `signal_source="text_fallback"` 경로가 자동으로 쓰인다.
    - **conflict_resolution은 편집장 응답 텍스트만으로 판정한다**(`agent_interactions`를
      의도적으로 안 넘김) — `ConflictResolutionConfig()` 기본값(한국어 마커
      "충돌"/"불일치" vs "해결"/"합의"/"결정" 이미 포함)이 그대로 맞아떨어져서
      커스텀 마커가 필요 없었다. 편집장 프롬프트가 "불일치를 명시적으로 언급한
      뒤 해결하라"고 요구하므로, 판정이 갈렸을 때 편집장 응답에 이 마커들이
      자연스럽게 등장한다.
    - **`PropagationConfig`(정보 전파 충실도)는 의도적으로 범위 밖으로 뺐다**:
      리뷰어의 자유 텍스트 근거를 `key_facts`로 어휘 매칭하려면 짧은 factoid가
      필요한데, 한국어는 공백 기준 토큰 분할이라 리뷰어 문장 전체를 key_fact로
      쓰면 fuzzy match가 쉽게 실패한다(threshold 조정으로 억지로 맞추기보다
      스코프에서 뺌 — 나머지 4개 지표만으로 Gate F가 이미 N/A를 벗어나는 걸
      증명하는 데 충분했다).
    - 실측(실제 Ollama): 정상 챕터 → 두 검토자 합의(consensus=1.0), 편집장 승인,
      `book-forge gate`의 Gate F가 **0.953(pass)**로 최초로 N/A를 벗어남을 확인.
      의도적으로 사실 오류(파이썬 리스트를 C++ `std::vector`로 잘못 서술)를 심은
      챕터에서는 두 검토자가 서로 다른 근거로 REVISE 판정, 편집장이 두 근거를
      모두 반영해 최종 REVISE로 결론 내는 것도 확인.

16. **`agents/code_consistency_checker.py`(코드-본문 정합성 검사)는 `hasattr()`만
    쓰면 안 된다 — `dataclasses.field(default_factory=...)` 필드는 클래스 레벨에
    노출되지 않는다(실측 확인: `hasattr(ScopeConfig, "allowed_tools")`가 `False`)**:
    `@dataclass`는 `default_factory`가 있는 필드에 클래스 속성을 남기지 않는다
    (인스턴스별로 계산해야 하므로 클래스 레벨엔 애초에 값이 없음). 이 프로젝트가
    실제로 겪은 버그(ScopeConfig가 경로가 아니라 도구 이름 기반이라는 걸 소스로
    직접 확인 안 했으면 잘못된 설계를 밀어붙였을 뻔했던 사례)를 재현하는 게 이
    체커의 목적인데, 정작 `ScopeConfig.allowed_tools`(실제로 있는 필드,
    `default_factory=list`)를 `hasattr()`로만 검사하면 거짓 음성(실제로 있는데
    "없다"고 오탐)이 났을 것이다. `_has_attr_or_field()`가 `hasattr()` 실패 시
    `dataclasses.fields(obj)`도 추가로 확인해 이 문제를 막는다 — 재검토 시
    `hasattr()` 단독 검사로 되돌리지 말 것.
    - **`None`/`ValueError` 같은 Python 표준 어휘를 대상 패키지 소속으로 오판하는
      실측 버그도 발견·수정했다**: 실제 Ollama가 생성한 ScopeConfig 설명 챕터에서
      "음수인 경우 `None`으로 보정됩니다" 같은 정상 문장의 백틱 `None`이 "본문이
      언급했지만 target_package에 없다"고 오탐으로 잡혔다(대문자 시작+소문자
      포함 4자 이상이라는 CamelCase 휴리스틱만으로는 `None`을 걸러내지 못함).
      `_BUILTIN_EXCLUSIONS = dir(builtins) | dir(typing)`(대문자로 시작하는
      이름만)를 백틱 심볼 필터에 추가해 해결 — Python 표준 예외/타입 이름은
      "그 패키지 소속이라고 주장한 적 없는" 정상 어휘이므로 애초에 검사 대상이
      아니다. 백틱 심볼 검증 로직을 건드릴 때는 이 제외 목록을 유지할 것.
    - CLI는 `book-forge draft ... --check-package <패키지명>`(옵트인, 기본
      검사 없음) — `run_batch_draft()`/`new --source`에도 동일하게 전파된다.
      content_type과 무관하게 동작하므로(narrative 챕터도 프로즈 중에 클래스명을
      언급) `demonstration_verifier.py`의 content_type 분기와 별개로 호출된다
      (`draft_cmd.py`의 `_print_code_consistency()`, `check_package`가 주어질
      때만 실행). LLM을 호출하지 않고 `importlib.import_module()`로 저자가
      CLI에서 명시적으로 지정한 패키지만 로드한다 — 임의 원격 코드 실행이
      아니다.

17. **`capstone` content_type은 `exercise`와 다른 생성 패턴이다 — 결과물이
    한 파일이 아니라 두 파일(템플릿+정답)이라는 게 핵심 차이다**: 9개 후보
    기능(AI Agent 강의 분석에서 도출)의 9번 항목("빈 템플릿 + 별도 정답")을
    구현한 것이다. `exercise`(`chapter_drafter.py`)는 "목표→실습 코드→해설"을
    한 파일에 담아 독자가 열자마자 정답이 보이지만, `capstone`
    (`agents/capstone_generator.py`)은 독자가 실제로 풀어볼 빈 템플릿(TODO
    스켈레톤)과 모범 정답+해설을 분리한다.
    - **한 번의 LLM 호출로 둘 다 받는다, 두 번 호출하지 않는다**:
      `=== TEMPLATE ===`/`=== SOLUTION ===` 구분자로 같은 응답 안에서 나눈다.
      두 번 호출하면(템플릿 생성 1회 + 정답 생성 1회) 서로 다른 컨텍스트에서
      나와 다른 문제를 다룰 위험이 있다(예: 템플릿은 리스트 실습인데 정답은
      딕셔너리 실습) — `parse_capstone_response()`가 관대하게 분리한다(구분자가
      없거나 순서가 뒤바뀌면 예외 없이 전체를 템플릿으로, 정답은 빈 문자열로
      폴백 — `parse_alternatives()`와 같은 원칙).
    - **정답은 `01_목차.md`가 모르는 사이드카 파일에 쓴다**: `draft_cmd.py`가
      `rc.path.with_name(rc.path.stem + "_정답" + rc.path.suffix)`로 챕터
      파일과 같은 디렉토리에 `Chapter_XX_제목_정답.md`를 쓴다. 별도
      `solutions/` 디렉토리를 만들지 않은 이유: `load_toc()`이 목차
      매니페스트만 파싱하고 디렉토리를 스캔하지 않는다는 게 이미 확인된
      사실이라(`build_toc_sidebar()`/`editor/server.py`/`html_builder.py`/
      `pdf_builder.py`/`slide_builder.py` 전부 `load_toc()` 경유), 목차에
      없는 파일은 어디서든 안전하게 숨겨진다 — 새 격리 메커니즘을 만들 필요가
      없었다. 실측(실제 Ollama): 빌드된 HTML에 정답 코드(`.reverse()` 등
      정답에만 있는 텍스트)가 전혀 섞이지 않음을 확인.
    - **`_STRICT_CONTENT_TYPES`(D)에 `capstone`도 포함시켰다** — exercise/diagram과
      같은 이유로, 실증이 필요한 콘텐츠는 소스 부족 상태로 생성하면 위험이
      더 크다.
    - `verify_demonstration()`(단일 문서 시그니처)로는 capstone을 처리할 수
      없다 — 템플릿/정답 두 문서를 함께 봐야 하므로 `verify_capstone
      (template_md, solution_md)`을 `draft_cmd.py`가 직접 호출한다
      (`verify_demonstration()`의 디스패치 대상이 아님, 재검토 시 착각하지
      말 것). 템플릿엔 TODO 마커 존재+문법 유효성을, 정답엔 TODO 부재+문법
      유효성을 확인한다.

18. **`book-forge chat`의 지속형 상호작용 강화는 `agent_evaluator.core.trackers.conversation.ConversationSession`을
    `monitor.conversation(session_id)`로 얻어 쓴 것이다, 새 대화 이력 관리 로직을
    만들지 않았다**: 처음 구현한 `chat_cmd.py`는 매 질문이 완전히 독립적인
    `answer_question()` 호출이라 "방금 말한 그거" 같은 이어지는 질문을 이해하지
    못했다. 두 가지를 나눠서 고쳤다 — 헷갈리지 말 것, 서로 다른 메커니즘이다:
    - **LLM이 실제로 이전 발화를 참조하게 하는 것**: `agents/chat_agent.py`의
      `answer_question()`에 `conversation_history: str = ""` 파라미터를 추가하고
      `CHAT_PROMPT`에 `--- 이전 대화 ---` 섹션으로 끼워 넣는다. `chat_cmd.py`가
      매 턴마다 Python 리스트(`history: list[tuple[str, str]]`)에서 최근
      `_MAX_HISTORY_TURNS=3`턴만 잘라 문자열로 포맷해 넘긴다 — `ConversationSession`
      자체는 이 프롬프트 조립에 관여하지 않는다(순수 참고용 메트릭 트래커일
      뿐, LLM 입력을 만들어주지 않음). `conversation_history`는 `rag_mode`의
      `context_arg="sources"`와 별개 채널이라 `HallucinationDetector`의 환각
      채점 기준(지식창고 발췌문)에는 영향을 주지 않는다 — 재검토 시 두 채널을
      섞지 말 것.
    - **세션 품질을 측정하는 것**: `chat_cmd.py`의 REPL 루프 전체를
      `with monitor.conversation(f"chat_{slug}") as conv:`로 감싸고, 매 턴
      끝에 `conv.turn(user=question, agent=answer)`를 호출한다. `with` 블록이
      정상 종료(`/exit`, EOF)하면 `ConversationSession.__exit__`이 자동으로
      `compute_metrics()`를 호출하고 `monitor.conversation_sessions`에 append한다
      (예외가 전파되면 스킵 — SDK 자체 동작, Book-forge가 따로 처리 안 함).
      계산되는 4개 지표(`context_retention`/`topic_coherence`/
      `progressive_depth`/`session_completion`)는 순수 Python 어휘 비교
      기반이라 LLM 호출이 없다. **Gate A-G 점수에는 반영되지 않는다** —
      `ConversationSession`은 CLAUDE.md 상단의 25개 Native Tracker 분류에서
      "operational support"(8종) 소속이다(재확인 완료), Gate 집계 로직
      (`gates/*/aggregate.py`)이 이걸 참조하지 않는다. `eval_results/chat.json`의
      최상위 `conversation_sessions` 키(중첩 아님, `extra_metrics` 밑이 아님 —
      실측 확인)에 턴별 기록+계산된 지표가 함께 저장된다.
    - 실측(실제 Ollama): "reverse() 메서드는 어떻게 동작해?" 다음에 "방금 말한
      그 메서드는 원본을 바꾸는거야 아니면 새로 만드는거야?"를 물었을 때, 두
      번째 답변이 지시어 "그 메서드"를 `reverse()`로 정확히 이해해 답함(대화
      이력 없이는 이 대명사 참조가 불가능) — `context_retention=0.60,
      topic_coherence=0.26, overall=0.49`로 실제 계산됨을 확인.

19. **`agents/sdk_version_pin.py`(SDK 버전 고정 메타데이터)는 코드-본문 정합성
    검사(항목 16)가 "무엇을 기준으로 판정하는지"를 프로젝트에 기록하는
    것이다 — 새 검증 로직이 아니라 기존 검사의 기준을 명시하는 메타데이터
    계층이다**: `--check-package`는 지금까지 "그 순간 설치된" 버전을 암묵적
    기준으로 삼았다 — 프로젝트를 오늘 0.9.9로 쓰고 몇 달 뒤 환경이 1.2.0으로
    올라간 채로 재검사하면, "본문이 틀렸다"와 "SDK가 바뀌어 기준 자체가
    달라졌다"를 구분할 방법이 없었다.
    - **"고정"은 최초 1회만 기록한다는 뜻이다 — 현재 설치 버전으로 자동
      갱신하지 않는다**: `pin_version()`이 `sdk_versions.json`에 이미 값이
      있으면 그대로 반환하고 아무것도 쓰지 않는다. 재검토 시 "설치 버전이
      바뀌었으니 자동으로 최신화" 같은 편의 기능을 추가하고 싶어질 수 있는데,
      그러면 "고정"의 의미 자체가 사라진다(드리프트를 감지할 기준점이
      없어짐) — 하지 말 것.
    - **버전 조회는 `importlib.metadata.version()`이지 `agent_evaluator.__version__`
      류의 속성이 아니다**: 패키지가 `__version__`을 노출하지 않아도(대부분의
      패키지가 안 함) 안정적으로 동작하고, `agent_evaluator`/`agent-evaluator`
      두 표기 다 정규화해 처리한다(실측 확인). 미설치/조회 불가 시
      `PackageNotFoundError`를 잡아 `None`으로 폴백한다 — 이 실패가
      `code_consistency_checker.py`의 검증 자체를 막지는 않는다(그쪽은
      `importlib.import_module()`로 별도 확인하는 완전히 다른 경로).
    - **드리프트 경고는 CLI 출력에만 나타난다, 검증 결과의 pass/fail을
      바꾸지 않는다** — 다른 D/C 검증 신호와 같은 철학("실패해도 초안 저장을
      막지 않는다", 참고용). `_print_code_consistency()`가 검증 실행 전에
      `check_version_drift()`를 호출해 경고를 먼저 출력하고, 검증 결과 옆에
      **고정된 버전**(현재 설치 버전이 아님)을 `(agent_evaluator 0.9.9 기준)`
      형태로 항상 표시한다 — 드리프트가 있을 때 "지금 뭘 기준으로 판정했는지"를
      혼동하지 않게.
    - 실측(실제 Ollama): 최초 `--check-package` 호출로 `sdk_versions.json`에
      실제 설치 버전(`0.9.9`)이 고정되는 것, 이후 파일을 수동으로 `0.5.0`으로
      바꾼 뒤 재실행하면 드리프트 경고가 뜨고 검증 결과에는 `(agent_evaluator
      0.5.0 기준)`(고정값)이 표시되는 것, 재실행이 `0.9.9`로 자동 되돌리지
      않는 것(고정 유지)을 모두 확인.

20. **`agents/code_example_verifier.py`(--execute-examples)는 항목 13("LLM이
    생성한 임의 코드를 자동으로 실행하지는 않는다")의 결정을 뒤집는 게 아니라
    그 결정 위에 별도의 명시적 옵트인 계층을 얹은 것이다 — 재검토 시 항목
    13과 모순된다고 착각하지 말 것. `exercise`/`diagram`/`capstone`/
    `code_consistency`의 기본 검증(문법·구조·심볼 존재)은 지금도 실행하지
    않는다. `--check-package`와 함께 `--execute-examples`를 명시적으로 켰을
    때만 이 모듈이 개입한다**:
    - **격리 방식은 in-process `exec()`가 아니라 `subprocess`다 — 사용자가
      명시적으로 이 방식을 선택했다(다른 대안: 구현 보류)**. 각 코드 블록을
      임시 디렉토리(`tempfile.TemporaryDirectory`)의 별도 파일에 써서
      `sys.executable`로 실행하고, 타임아웃(기본 10초,
      `DEFAULT_TIMEOUT_SECONDS`)을 건다. `exec()`를 안 쓰는 이유: 크래시가
      CLI 프로세스 자체를 죽이지 않고, 부모 프로세스 메모리(API 키가 담긴
      환경 변수 등)에 코드가 직접 접근할 수 없다. **단, 파일시스템/네트워크
      접근은 OS 수준으로 격리되지 않는다** — 컨테이너 없는 순수 Python
      subprocess의 한계이며, README "알려진 한계"에 명시했다. 신뢰할 수 없는
      `--source`와 함께 쓰지 말 것.
    - **capstone은 template이 아니라 solution만 실행 대상이다**: template은
      `TODO`/`raise NotImplementedError`로 의도적으로 미완성이므로 실행하면
      항상 "실패"가 나와 무의미하다. `_draft_one_chapter()`가
      `content_type == "capstone"`이면 `solution_md`를, 그 외엔 `draft_md`를
      `verify_code_execution()`에 넘긴다 — 재검토 시 이 분기를 빠뜨리면
      capstone 챕터마다 항상 거짓 실패가 뜬다.
    - **실행 실패해도 초안 저장을 막지 않는다 — 원 설계 문서의 "실패 시
      초안 반려"는 채택하지 않았다(사용자 확인 후 결정)**: 지금까지
      exercise/diagram/capstone/code_consistency 전부가 "경고만, 저장은
      유지" 원칙을 일관되게 지켜왔다 — 이 원칙을 이 검증기만 예외로 두면
      다른 검증기와의 UX 일관성이 깨진다. `_print_code_execution()`이 다른
      `_print_*` 헬퍼와 동일한 출력 패턴(`▶️  코드 실행 검증: ✅/⚠️`)을 쓴다.
    - `--execute-examples`는 `--check-package` 없이 단독으로 쓸 수 없다
      (`draft()`/`new()` 양쪽에 `if execute_examples and not check_package:
      raise click.ClickException(...)` 검증 있음) — "이 SDK를 대상으로
      검증한다"는 맥락 없이 코드 실행만 단독으로 여는 옵션을 만들지 않기로
      했다(스코프를 좁게 유지).
    - 실측(실제 Ollama): 정상 실습 코드(`reversed()`/슬라이싱으로 리스트
      뒤집기)가 실제 subprocess 실행에 성공함을 확인. 존재하지 않는 메서드를
      "실제로 있다고 믿게" 유도하는 소스로 재시도했을 때 LLM이 `try/except
      AttributeError`로 방어적으로 코드를 작성해 실행이 여전히 성공한 것도
      관찰함(검증기 버그 아님 — 오프라인 결정론적 테스트로 문법 오류/런타임
      예외(AssertionError/ImportError)/타임아웃 3가지 실패 경로는 별도로 이미
      검증 완료).

21. **`knowledge/code_index.py`(구조적 코드 인덱싱, 일반 능력 H)는
    `load_code_repo_source()`의 청크 검색을 대체하는 게 아니라 보강하는
    것이다 — 별도 저장소·별도 검색 경로를 만들지 않았다**: "이 프로젝트에
    어떤 모듈이 있는가"류 구조 질문은 텍스트 유사도 검색으로 잘 안 잡힌다
    (import문이 청크 경계에서 잘리거나, 애초에 그래프 구조가 청크 텍스트
    나열에는 없음). `build_structure_index()` + `format_structure_summary()`가
    만든 결과를 `chunk_text()`로 쪼개 **기존 chunks 리스트에 그대로 append**
    한다 — `KnowledgeStore`/`embeddings.py` 등 검색 파이프라인 전체를 하나도
    안 건드리고, 그냥 검색 가능한 청크가 하나 더 늘어난 것처럼 취급된다.
    - **Python(`.py`)만 지원한다 — 의도적 스코프 축소, 다국어 파서를 추가하지
      않는다**: `ast`가 표준 라이브러리라 새 의존성이 필요 없다는 게
      이유다(PDF는 `pypdf`, HTML은 stdlib `html.parser`를 쓰는 기존
      "무거운 파싱 라이브러리를 안 쓴다" 원칙과 같은 선상). tree-sitter 등
      다국어 지원은 재검토 시에도 신중할 것 — 코드 저장소 어댑터가 이미
      `_CODE_EXTS`(`.ts`/`.go`/`.rs`/`.java`/`.rb` 등)를 다국어로 지원하는데,
      구조 인덱싱은 Python만 되므로 다른 언어 저장소는 구조 요약 없이 기존
      청크 검색만으로 커버된다(자연스러운 축소 — `.py`가 하나도 없으면
      `format_structure_summary()`가 빈 문자열을 반환해 조용히 스킵됨,
      예외 없음).
    - **내부/외부 의존 분류는 완벽한 import 해석기가 아니라 휴리스틱이다**:
      import의 첫 세그먼트가 인덱싱 루트 디렉토리 자신의 이름이거나 바로
      아래 서브디렉토리 이름과 같으면 "내부"로 분류한다(`_internal_import_roots()`).
      상대 import나 `sys.path` 조작까지는 못 따라간다 — "정확한 의존 그래프"가
      아니라 "대략 구분하는 근거"가 목적이라는 걸 재검토 시 잊지 말 것.
      실측(Book-forge 자신의 `src/book_forge` 인덱싱): `from
      book_forge.agents.prompts import X`가 정확히 "내부"로, `agent_evaluator`
      import가 정확히 "외부"로 분류됨을 확인.
    - **문법 오류 파일은 조용히 건너뛴다, 저장소 전체 인덱싱을 중단시키지
      않는다**: `extract_module_summary()`가 `ast.parse()`의 `SyntaxError`를
      잡아 `None`을 반환한다 — `demonstration_verifier.py`의 다른 검증기들과
      같은 "실패해도 전체를 막지 않는다" 원칙.
    - `load_code_repo_source(..., include_structure_index=True)`가 기본값
      True다 — LLM을 호출하지 않고 결정론적·빠르므로(순수 `ast.parse()`)
      옵트아웃 방식을 택했다(다른 새 검증기들이 옵트인인 것과 다른 이유:
      이건 검증이 아니라 검색 품질을 높이는 소스 추가이고, 실패 시 위험이
      없다 — LLM 코드 실행(`--execute-examples`)처럼 명시적 동의가 필요한
      위험이 아님).
    - 실측(실제 Ollama): Book-forge 자신의 `agents/` 패키지(18개 모듈)를
      `--source`로 써서 "agents 패키지 구조 분석" 챕터를 생성했더니,
      `PlannerAgent`/`AlternativeSuggesterAgent`/`ChiefEditorAgent` 등 실제
      클래스·역할과 `demonstration_verifier.py`/`diagram_generator.py` 같은
      실제 모듈명을 정확히 서술함을 확인.

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
