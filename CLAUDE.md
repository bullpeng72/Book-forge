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

22. **로컬 코드베이스 대상 검증(일반 능력 I)은 `--check-package`에 새 CLI
    플래그를 추가하지 않고, `Path(check_package).is_dir()`로 자동 감지해
    기존 3개 검증기(code_consistency_checker/sdk_version_pin/code_example_verifier)를
    로컬 모드로 전환하는 방식이다 — `_SourcePath`가 URL/로컬 경로를 자동
    구분하는 것과 같은 UX 패턴을 재사용한 것이지 새로 고안한 게 아니다**:
    - **`code_consistency_checker.py`의 로컬 모드는 H(구조적 코드 인덱싱)의
      정적 분석을 그대로 재사용한다, 새 파싱 로직을 만들지 않았다**:
      `verify_code_consistency_local()`이 `code_index.build_structure_index()`로
      대상 디렉토리를 훑고, `code_index.internal_import_roots()`(H를 위해
      만든 함수를 이제 두 모듈이 공유 — 원래 `_`prefix로 비공개였던 걸
      공개로 승격했다)로 "이 import가 분석 대상 프로젝트 소속으로 보이는가"를
      거른다.
      - **정확한 서브모듈까지는 확인하지 않는다 — 평평한 심볼 테이블 대조다**:
        로컬 디렉토리 경로를 dotted import 경로(`book_forge.agents.x`)로
        신뢰성 있게 매핑할 방법이 없다(target_dir가 패키지 루트인지 그
        서브디렉토리인지 알 수 없음). 그래서 "정확히 어느 파일에 있는가"가
        아니라 "대상 디렉토리 전체 어딘가에 존재하는가"만 본다 — installed
        패키지 모드(`importlib`, 서브모듈 단위로 정확히 확인)보다 느슨한
        보장이라는 걸 재검토 시 기억할 것.
      - **import 필터는 첫 세그먼트가 아니라 임의 세그먼트로 대조한다 —
        실측으로 발견한 실패 케이스를 고친 것**: `target_dir`가 실제 패키지
        루트(`src/book_forge`)가 아니라 그 서브디렉토리(`src/book_forge/agents`)를
        가리키면, `internal_roots`엔 `"agents"`만 들어있는데 import는
        `"book_forge.agents.x"`로 시작해 첫 세그먼트 비교로는 못 잡았다
        (`test_verify_code_consistency_local_matches_when_target_is_subdirectory`로
        회귀 고정). `set(module_path.split(".")) & internal_roots`로
        수정했다 — 오탐 위험은 낮다(최종적으로 known_symbols 대조가 필터
        역할을 함).
    - **`sdk_version_pin.py`의 로컬 버전은 git 커밋 해시(짧게)+dirty
      여부다 — agent-evaluator 자신의 `agent_version="auto"`(git 커밋+dirty
      해시) 패턴과 같은 원리를 그대로 가져왔다**: `resolve_local_version()`이
      `git -C <dir> rev-parse --short HEAD` + `git status --porcelain`을
      호출한다. git이 없거나 저장소가 아니면(또는 명령 타임아웃) 예외 없이
      `None`으로 폴백 — 코드-본문 정합성 검사 자체는 버전 추적 없이도
      계속 정상 동작한다(부가 기능이라는 위치를 지킴). `sdk_versions.json`의
      dict 키는 `_normalize_target_key()`로 로컬 디렉토리를 **절대 경로로
      정규화**한다 — `./toylib`와 `/abs/path/toylib`처럼 상대/절대 경로를
      다르게 써도 같은 고정 기록을 재사용하게 하기 위함(정규화 안 하면
      같은 디렉토리인데 다른 키로 중복 기록됨).
    - **`code_example_verifier.py`는 대상 디렉토리를 subprocess의
      `PYTHONPATH`에 추가해 설치 안 된 로컬 import를 풀리게 한다 —
      실측으로 진짜 버그를 하나 잡았다**: 처음 구현했을 때 `extra_pythonpath`를
      **상대 경로 그대로** `PYTHONPATH`에 넣었는데, subprocess의 `cwd`가
      임시 디렉토리(`tempfile.TemporaryDirectory`)라 상대 경로가 엉뚱한
      위치를 가리켜 `ModuleNotFoundError`가 계속 재현됐다 — `_build_execution_env()`가
      `extra_pythonpath.resolve()`로 절대 경로 정규화한 뒤에야 해결됨
      (`test_verify_code_execution_accepts_relative_extra_pythonpath`로
      회귀 고정). 대상 디렉토리 자신과 그 부모 디렉토리 둘 다 추가한다 —
      target_dir 자체가 import 가능한 패키지인지(부모가 필요), 아니면
      target_dir 안에 낱개 모듈이 있는지(target_dir 자체가 필요) 미리 알
      수 없어서다(휴리스틱, H의 "완벽한 그래프 아님"과 같은 철학).
    - 실측(실제 Ollama): 어디에도 설치되지 않은 독립 로컬 패키지(`toylib`,
      pip install도 editable install도 안 함)를 만들어
      `--check-package <경로> --execute-examples`로 검증했다. 생성된 실습
      챕터가 `from toylib.calculator import make_calculator`를 실제로
      import해 subprocess 실행에 성공(PYTHONPATH 주입 없이는 애초에 이
      import가 실패할 수밖에 없는 패키지였음). git 저장소로 만든 뒤
      재실행하니 `(toylib git 6eb099b 기준)`처럼 커밋 해시 기반 버전
      고정도 정상 동작함을 확인.

23. **`llm/provider.py`의 `OllamaLLM.generate()`는 페이로드에 항상
    `think: False`를 보낸다 — 실제 사용자 환경(`OLLAMA_MODEL=qwen3.6:35b-mlx`)에서
    챕터 파일이 통째로 빈 채 저장되는 진짜 버그를 재현하고 고친 결과다.
    재검토 시 이 옵션을 빼지 말 것**: 이 세션 내내 격리된 `/tmp` 테스트는
    전부 `qwen3-coder:latest`(비추론 모델)로만 검증했었는데, 실제 사용자의
    실제 프로젝트(`AI_에이전트_평가_입문`)에 `book-forge draft`를 처음
    돌렸을 때 Gate A/C/D가 전부 `0.000`으로 나오고 챕터 파일이 0바이트로
    저장되는 걸 발견했다.
    - **근본 원인**: Ollama의 `/api/generate`는 Qwen3 계열 같은 "추론(thinking)"
      모델의 사고 과정을 `response`가 아니라 별도 `thinking` 필드에 담는다.
      `num_predict`(=`max_tokens`) 예산을 사고 과정에 다 써버리면
      (`done_reason="length"`) `response`는 끝까지 빈 문자열로 남는다 —
      실측: `curl`로 직접 `qwen3.6:35b-mlx`에 짧은 프롬프트를 보냈는데도
      `response=""`, `thinking="Here's a thinking process..."`(300 토큰을
      다 쓰고도 답변 시작 전)이 재현됨.
    - **수정**: 요청 페이로드에 `"think": False`를 추가했다 — 이 값을 보내면
      추론 모델도 사고 과정을 건너뛰고 바로 `response`에 답을 채운다
      (`done_reason="stop"`으로 정상 종료). 추론을 지원하지 않는 모델
      (`qwen3-coder:latest` 등)에 이 옵션을 보내도 에러 없이 무시된다 —
      실측 확인, 항상 켜둬도 안전하다.
    - `tests/test_llm_provider.py::test_ollama_generate_sends_think_false`가
      페이로드에 `think: False`가 항상 포함되는지 회귀 고정한다.
    - **교훈**: 이 세션의 모든 실제 Ollama 검증은 `qwen3-coder:latest`
      (도구/코드 특화, 비추론) 모델로만 했다 — 추론 모델 특유의 실패 모드는
      실제 사용자 환경에서 실제 사용자의 모델로 돌려보기 전까지 드러나지
      않았다. 앞으로 새 LLM 호출 경로를 추가하거나 리팩터링할 때, 격리된
      `/tmp` 테스트만으로 "검증 완료"라고 판단하지 말 것 — 가능하면 실제
      사용자 `.env`/실제 프로젝트로도 최소 1회는 돌려봐야 이런 모델별 실패
      모드를 잡는다.

24. **`agents/code_consistency_checker.py`의 설치된-패키지 모드는 최상위
    네임스페이스만 보는 한계가 있었다(SPEC.md 항목 L) — `_walk_package_symbols()`로
    서브모듈 전체를 스캔하는 폴백을 추가해 고쳤다.** 실전 6챕터 집필
    (`AI_에이전트_평가_입문` 프로젝트)에서 `Settings`(agent_evaluator.config),
    `KoreanRAGDatasetGenerator`(agent_evaluator.datasets),
    `LiveGuardrail`(agent_evaluator.gates.live_guardrail) 세 번 모두 실존하는
    클래스인데 `agent_evaluator` 최상위에 재노출이 안 됐다는 이유만으로
    오탐(없음)이 났다 — `importlib.import_module(target_package)` +
    `hasattr()`은 딱 그 모듈 객체가 들고 있는 속성만 보기 때문이다.
    - **수정**: `pkgutil.walk_packages()`로 target_package 산하 서브모듈을
      전부 import해 공개 멤버 이름을 평평한 집합으로 모으는
      `_walk_package_symbols()`(모듈별 1회만 계산 후 캐시)를 추가했다. 백틱
      심볼 체크에서 `_resolve_dotted(root_module, path)`가 실패해도, **path의
      첫 세그먼트가 애초에 최상위에 없는 경우에만**(재노출 누락 케이스) 이
      평평한 테이블로 재확인한다.
    - **의도적으로 좁힌 범위**: `ScopeConfig`가 최상위에 있지만
      `ScopeConfig.path`처럼 실제로 없는 필드를 언급한 경우는 이 폴백을
      타지 않는다 — base(`ScopeConfig`)가 최상위에서 이미 보이므로 원래
      경로(`_resolve_dotted`)로 판정이 끝나고, 폴백은 "base 자체가 안 보일
      때"만 개입한다. 폴백을 무조건 적용했다면 `ScopeConfig.path` 같은 진짜
      오류(`tests/test_code_consistency_checker.py::test_verify_code_consistency_catches_nonexistent_field_reference`)를
      놓쳤을 것 — 실제로 처음 구현했을 때 이 회귀가 나서 조건을 좁혔다.
      import 문(`from X import Y`) 체크는 원래부터 `importlib.import_module(module_path)`로
      정확한 서브모듈을 직접 import하므로 이 문제와 무관하다(백틱 심볼
      체크만 해당).
    - 로컬 모드(`verify_code_consistency_local`, 일반 능력 I)는 원래부터
      "평평한 심볼 테이블" 방식이었다 — 이번 수정은 그 발상을 설치된
      패키지 모드로 확장한 것뿐, 새 판정 로직이 아니다.

25. **`book-forge knowledge status`/`reset`(일반 능력 J, SPEC.md 항목 J)는
    `KnowledgeStore.add()`가 중복 제거를 안 하고 `collect_sources_into_store()`가
    항상 append만 하는 구조적 한계를 CLI 레벨에서 우회한다.** 실전 6챕터
    집필(`AI_에이전트_평가_입문`) 중 OpenCode 플러그인 TS 파일이 한 번 섞여
    들어간 뒤 그 심볼(`EventSessionIdle` 등)이 이후 여러 챕터의 검색 결과를
    계속 오염시키는 걸 실측으로 겪었다 — 당시 유일한 해결책은
    `knowledge/store.json`을 직접 `rm`하는 것뿐이었다.
    - `knowledge/lifecycle.py::summarize_store()` — 청크의 `# 파일:`/`# 출처:`
      태그(`sources.py`가 이미 청크 앞에 붙이던 것)를 정규식으로 역파싱해
      소스별 청크 수를 센다. 새 태깅 로직이 아니라 기존 태그의 재활용이다.
    - `cli/commands/knowledge_cmd.py` — `status`는 `summarize_store()` 결과를
      출력만 하고, `reset`은 `store_path.unlink()`뿐이다(확인 프롬프트 기본,
      `--yes`로 스킵). 둘 다 판정 로직이 없어 새 회귀 위험이 거의 없다.
    - **집계는 정확한 감사가 아니라 참고용**: `chunk_text()`의 overlap
      크기에 따라 파일 하나의 두 번째 이후 청크엔 태그 줄이 안 남을 수
      있고, PDF 소스는 애초에 태깅하지 않는다 — 태그를 못 찾은 청크는
      "(태그 없음)"으로 묶는다. 실측(`AI_에이전트_평가_입문` 실제 스토어,
      83개 청크)으로 확인: 태그가 남은 건 5개뿐(78개가 "(태그 없음)")이라
      이 한계가 실제로 두드러진다 — 향후 정확도를 높이려면 태그를 매
      청크 앞에 반복해서 붙이는 쪽으로 `sources.py`를 바꿔야 하지만, 이번
      범위(J)는 "있는 태그를 최대한 활용한 참고용 요약"까지만 다룬다.

26. **`book-forge plan --revise`는 목차 개정 이력을 이제 `01_목차.md`에
    자동으로 남긴다(일반 능력 O, SPEC.md 항목 O)** — Media/AOO의 목차
    파일이 "2026-07-14 개정 ①/②/③"처럼 날짜별 변경 사유를 누적 기록하는
    관행을 참고해, 기존엔 조용히 덮어쓰던 `01_목차.md`에 같은 관행을
    자동화했다.
    - `agents/review_loop.py::run_review_loop()`에 옵트인 `on_feedback`
      콜백을 추가했다 — 승인으로 끝난 라운드(피드백 없음)는 호출되지 않고,
      실제로 개정을 유발한 라운드의 피드백 원문만 전달된다.
    - `models.py::append_toc_revision_entries()` — `on_feedback`이 모은
      피드백 목록을 받아 `## 개정 이력` 섹션을 문자열 조작만으로 갱신한다
      (마크다운 재파싱 없음, 새 LLM 호출 없음). 기존 섹션이 있으면
      기존 항목 뒤에 이어붙이고, 없으면 파일 맨 위에 새로 만든다.
    - `plan_cmd.py`는 `toc_feedback_log: list[str]`을 `on_feedback`으로
      연결하고, 목차를 파일에 쓰기 직전 `toc_feedback_log`가 비어있지 않을
      때만(=피드백 없이 바로 승인된 경우 제외) `append_toc_revision_entries()`를
      호출한다.
    - **빌드 파이프라인에 영향 없음**: 사이드바/챕터 목록은
      `parse_toc_manifest()`가 ` ```toc ` 코드 블록만 정규식으로 뽑아내므로,
      그 위에 붙는 `## 개정 이력` H2 헤딩은 무시된다 — 실측으로
      `book-forge build html`이 개정 이력이 붙은 목차에서도 정상 동작함을
      확인했다.
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경): 6챕터
      목차를 승인한 뒤 `plan --revise`에서 "목차를 4개 챕터로 줄여줘"라고
      피드백을 주니, 목차가 실제로 4챕터로 줄어들며 `01_목차.md` 맨 위에
      `## 개정 이력\n- **2026-07-24**: 목차를 4개 챕터로 줄여줘`가 정확히
      기록됐다.

27. **`agents/prompts.py`의 `DRAFT_PROMPT`/`DRAFT_PROMPT_EXERCISE`에 고정 섹션
    두 개를 추가했다(일반 능력 M, SPEC.md 항목 M)** — Media/AOO의 모든
    챕터가 공유하는 "학습 목표 → 본문 → 핵심 요약" 틀과 달리, 기존
    `DRAFT_PROMPT`는 "`# Chapter N: 제목`으로 시작, `## `로 소제목만
    나누라"는 최소 지시뿐이라 챕터마다 절 구성이 제각각이었다.
    - 본문 시작에 `## 이 챕터에서 배우는 것`(2~3개 불릿), 본문 끝에
      `## 이 챕터의 핵심`(3개 내외 불릿)을 요구하도록 두 프롬프트를 모두
      수정했다. exercise의 기존 `## 목표`/`## 실습`/`## 해설` 지시는
      그대로 유지하고 앞뒤에만 새 섹션을 끼워 넣었다.
    - **의도적으로 뺀 것**: "대상 독자"(기획안 단계와 중복), 페르소나별
      TIP 박스, "다음 챕터" 링크(다권 전체의 순서/페르소나 정보가 챕터
      단위 프롬프트엔 없어 프롬프트만으로 신뢰성 있게 못 만든다 — 억지로
      만들면 부정확한 링크가 나올 위험, 정직한 스코프 축소).
    - **검증 없음, 프롬프트 지시일 뿐**: `demonstration_verifier.py`는 이
      두 섹션의 존재를 검사하지 않는다 — Gate C(HallucinationDetector)
      범위 밖이고, 강제하면 소스가 빈약한 챕터에서 거짓 요약을 억지로
      만들어낼 위험이 검증 부재보다 더 나쁘다고 판단했다.
    - `tests/test_chapter_drafter.py`의 기존 회귀
      (``"`## `로 소제목을 나누어" in result``)가 계속 통과하도록 그
      정확한 문구를 새 구조 안에도 그대로 유지했다 — 프롬프트 문구
      자체를 검증하는 테스트라 문구를 지우면 깨진다.
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경): 변수/자료형
      챕터를 `--source`로 생성하니 정확히 `## 이 챕터에서 배우는 것`(3개
      불릿)으로 시작해 본문을 거쳐 `## 이 챕터의 핵심`(3개 불릿)으로
      끝나는 걸 확인했다.

28. **`KnowledgeStore.query_with_scores(max_per_source=...)`(일반 능력 K,
    SPEC.md 항목 K)를 구현하다가, 그 전제 조건인 `sources.py`의 청크 태깅이
    애초에 깨져 있었다는 걸 발견해 같이 고쳤다.** 실전 Chapter 3 집필에서
    `quick_eval.py`(ANSI 색상 헬퍼) 청크가 61%를 차지해 검색 결과를
    지배하며 엉뚱한 주제로 챕터가 생성된 걸 실측으로 확인했었다(이전
    세션 기록) — `max_per_source`로 소스별 상한을 두는 것까지는 계획대로였다.
    - **구현 중 발견한 선행 버그**: `load_code_repo_source()`가 파일 전체
      앞에 `# 파일: xxx` 태그를 붙인 **뒤** `chunk_text()`로 잘랐다 — 그러면
      여러 청크로 쪼개지는 큰 파일은 첫 청크만 태그를 갖고 나머지는 태그가
      없다. `max_per_source`는 이 태그로 소스를 식별하므로, 정작 잡아야 할
      대형 파일(quick_eval.py 같은)의 청크 대부분을 식별하지 못해 조용히
      무력화된다 — 재현 스크립트로 실측: `quick_eval.py`를 195개 청크로
      쪼갰을 때 태그가 남은 건 1개뿐이었다. `load_url_source()`도 같은
      패턴(`# 출처: url` 태그)으로 같은 문제를 갖고 있었다.
    - **수정**: `_tag_each_chunk(chunks, tag)`를 추가해, 먼저 `chunk_text()`로
      자른 뒤 매 청크 앞에 태그를 다시 붙이도록 두 함수를 고쳤다(청크가
      약간 길어지는 것 외 부작용 없음). `knowledge/lifecycle.py`의
      `summarize_store()`(항목 25, J)도 같은 태그를 쓰므로 이 수정으로
      같이 정확해졌다.
    - `store.py::query_with_scores()`는 `max_per_source=None`(기본,
      기존 동작 그대로)이면 원래 top_k만 반환하고, 정수가 주어지면
      순위대로 훑으며 소스별 카운트가 상한을 넘는 청크는 건너뛴다. 태그
      없는 청크(PDF 등)는 식별이 안 되므로 무조건 통과(안전한 폴백).
    - `draft_cmd.py`에 `--max-per-source N` 옵트인 CLI 옵션을 추가해
      `_draft_one_chapter()`/`run_batch_draft()`를 거쳐
      `query_with_scores()`까지 그대로 전달했다.
    - 실측(실제 Ollama 임베딩, agent_evaluator 자신의 `quick_eval.py`
      (195개 청크)/`metric_adapters.py`/`framework_integrations.py` 3개
      파일로 원래 실측 사례 재현): 수정 전엔 태그 무력화 때문에
      `max_per_source=2`를 줘도 top_k=8 결과가 여전히 8개 전부
      `quick_eval.py`였다 — 태깅 수정 후 재현하니 `quick_eval.py` 2개,
      `framework_integrations.py` 2개, `metric_adapters.py` 2개로 정확히
      분산됐다. 이 확인 없이는(재현 스크립트를 실제 Ollama로 두 번 돌려
      전후를 비교하지 않았다면) 태깅 버그를 놓치고 "구현 완료"로 잘못
      보고했을 뻔했다.

29. **`book-forge draft`가 URL 소스로 챕터를 생성하면 `## 참고 자료` 섹션을
    자동으로 붙인다(일반 능력 N, SPEC.md 항목 N — 범위를 의도적으로 좁힌
    버전).** Media/AOO 대비 품질 분석에서 나온 가장 큰 격차(진짜 웹 검색
    자동화)를 그대로 구현하지 않고, "저자가 이미 --source로 지정한 URL
    중 실제로 쓰인 것만 인용 목록으로 조립"까지로 스코프를 축소했다 —
    검색 자동화는 API 키/외부 서비스 의존성이 얽혀 이 라운드의 다른
    항목들과 성격이 달라 별도 후속 항목으로 미뤘다.
    - `draft_cmd.py::_cited_url_sources(scored)` — `query_with_scores()`가
      실제로 top-k에 뽑은 청크 중 `# 출처:` 태그로 시작하는 것만 중복 없이
      순서대로 뽑는다. `_append_references_section(draft_md, urls)` — 빈
      목록이면 no-op, 아니면 챕터 본문 끝에 `## 참고 자료` 섹션을 붙인다.
      둘 다 LLM을 호출하지 않는다 — "출처를 나열해달라"고 LLM에게
      요청하면 존재하지 않는 출처를 지어낼 환각 위험이 있어, draft_cmd.py가
      이미 알고 있는 태그 정보만으로 코드로 직접 조립했다.
    - **항목 28(K)의 태깅 수정이 이 기능의 실질적 전제 조건이었다**:
      `sources.py`가 매 청크에 태그를 다시 붙이도록 고치기 전이었다면,
      여러 청크로 쪼개지는 긴 웹페이지는 첫 청크만 인용되고 나머지는
      누락됐을 것이다 — K를 먼저 고친 순서가 우연히 N에도 도움이 됐다.
    - 콘텐츠 유형(narrative/reference_table/diagram/exercise/capstone)과
      무관하게 전부 적용된다 — `_draft_one_chapter()`의 content_type 분기
      **이후**, 파일 쓰기 **직전**에 `scored`(분기 이전에 이미 계산된
      검색 결과)를 그대로 재사용해 붙이므로 새 검색 호출이 없다.
    - 오프라인 `CliRunner` 테스트(`test_draft_appends_references_section_for_url_sources`)로
      `--source https://...`가 실제로 챕터 파일 말미에 `## 참고 자료`를
      붙이는 것까지 확인했다 — 이 기능은 결정론적 후처리(LLM 출력에
      의존하지 않음)라 실제 Ollama E2E보다 오프라인 테스트가 더 적합하다고
      판단해 별도 실측은 생략했다(K 항목에서 이미 태깅 메커니즘 자체는
      실제 Ollama 임베딩으로 검증됨).

30. **`book-forge research`(일반 능력 N 전체 범위, SPEC.md 항목 "N(추가)")로
    항목 29에서 의도적으로 미룬 "진짜 검색 자동화"를 이어서 구현했다** —
    챕터 제목 → 검색 쿼리 생성(LLM) → 실제 웹 검색 → 후보 URL 수집 →
    저자 선택 → 지식창고 추가.
    - **검색 백엔드 선택은 사용자에게 직접 확인**: API 키 필요 없는
      DuckDuckGo HTML(`html.duckduckgo.com/html/`), Tavily API(유료/키
      필요, 더 안정적), 범용 검색 API 엔드포인트 설정 세 가지를 제시했고
      사용자가 DuckDuckGo HTML을 선택했다 — Book-forge의 "API 키 없이
      바로 시작" 원칙과 일치, 새 pip 의존성도 없음(`requests`+표준
      라이브러리 `html.parser`만 사용, `knowledge/sources.py`가 이미 쓰는
      "무거운 파서 라이브러리를 추가하지 않는다" 원칙과 동일).
    - `knowledge/web_search.py::search_web(query, max_results)` —
      `_DuckDuckGoResultParser`(HTMLParser 서브클래스)가 결과 페이지의
      `<a class="result__a">`(제목)/`<a class="result__snippet">`(요약)만
      뽑는다. 파서를 짜기 전에 실제 DuckDuckGo 응답을 `curl`로 직접
      받아 마크업을 확인한 뒤 구현했다(추측으로 안 짬).
    - **실측으로 발견한 진짜 버그**: 링크 추출 로직을 리다이렉트 형식
      (`//duckduckgo.com/l/?uddg=<인코딩된 URL>&rut=...`)만 처리하도록
      짰다가, 영어 쿼리("python asyncio tutorial")로는 통과했지만 실제
      `book-forge research`를 **한국어** 챕터 제목으로 돌려보니 후보가
      통째로 0개가 나왔다. 원인을 다시 `curl`로 확인해보니 DuckDuckGo가
      한국어 쿼리에는 리다이렉트 링크 대신 **절대 URL을 href에 그대로**
      준다는 걸 발견했다(같은 세션 안에서 쿼리 언어에 따라 형식이 다름).
      `_extract_target_url()`이 `uddg` 파라미터가 있으면 리다이렉트로,
      없고 http(s) 절대 URL이면 그대로 대상으로 인정하도록 고쳐 두 형식
      모두 처리한다. `tests/test_web_search.py`에 두 형식 각각의 실제
      캡처 응답을 축약한 fixture로 회귀 테스트를 고정했다 — 하나만
      테스트했다면 이 버그를 코드 리뷰만으로는 못 잡았을 것이다.
    - `agents/research_agent.py::build_generate_search_queries()` +
      `parse_search_queries()` — 챕터 제목에서 검색 쿼리 2~3개를 생성한다
      (`agents/alternative_suggester.py`의 "관대한 파싱, 실패해도 빈
      리스트만 반환" 원칙과 동일). `cli/commands/research_cmd.py`가
      쿼리 생성 실패(형식 위반) 시 챕터 제목 자체를 쿼리로 쓰는 폴백을
      한다.
    - **신뢰도 자동 평가는 하지 않는다**: 1차/2차 출처 분류 같은 판단을
      LLM에게 맡기지 않고, 후보 목록(제목+요약+URL)을 저자에게 보여주고
      번호로 채택 여부를 직접 고르게 한다(`_select_candidates()`) —
      `book-forge plan`의 승인 루프와 같은 "최종 판단은 저자" 원칙을
      의도적으로 재사용했다. LLM이 안정적으로 못 하는 판단을 억지로
      자동화하는 것보다 사람이 제목/요약을 훑어보는 편이 더 신뢰할 수
      있다는 판단.
    - 채택된 URL은 `draft_cmd.py::collect_sources_into_store()`를 그대로
      재사용해 지식창고에 추가한다 — 새 저장 로직 없음.
    - **`book-forge draft`가 `--source` 없이도 동작하도록 확장**했다 —
      지식창고가 이미 있으면(`book-forge research`로 채웠거나 이전
      `draft` 호출로 이미 존재하면) `--source` 생략을 허용하고 기존
      지식창고를 그대로 쓴다. 지식창고가 아예 없는 프로젝트에서
      `--source` 없이 부르는 건 기존처럼 에러(빈 지식창고로 조용히
      진행해 근거 없는 초안이 나오는 걸 방지) — 이 완화가 없으면 저자가
      research로 지식창고를 채워도 draft에 다시 아무 `--source`나
      억지로 지정해야 하는 어색한 흐름이 됐을 것이다.
    - 실측(실제 DuckDuckGo + 실제 Ollama, `qwen3-coder:latest`, `/tmp`
      격리 환경): "비동기 프로그래밍이란?" 챕터로 `book-forge research`를
      돌려 실제 한국어 블로그·GitHub 소스 6개를 지식창고에 추가했고,
      이어서 `book-forge draft ...`(`--source` 없이)로 생성한 챕터가
      정상적으로 초안을 만들며, 실제로 인용된 URL 3개가 챕터 말미
      `## 참고 자료`(항목 29)에 자동으로 나타나는 것까지 파이프라인
      전체를 확인했다.

31. **슬라이드 파이프라인의 세 가지 실측 결함(P/Q/R, SPEC.md 2부)을
    `slide_builder.py` 한 곳에서 함께 고쳤다.** Book-forge 자신의
    `src/book_forge/agents/`를 --source로 실제 강의자료를 만들어보고
    발견했다 — "프로젝트 코드 → 도서(html/pdf) → 강의자료(slide)" 파이프라인의
    부족한 점을 찾아달라는 요청에 대한 실측 조사 중 나온 결과다.
    - **P(코드 블록 손실)**: `condense_section()`에 섹션 전체(코드 포함)를
      그대로 넘기면 LLM이 코드를 프로즈 요약으로 바꿔버린다 — 실측: 코드
      예제 4개짜리 챕터로 슬라이드를 만들었더니 결과 HTML에 `<pre>`/`<code>`
      가 0개였다. `extract_code_blocks()`로 코드/mermaid 펜스를 LLM 호출
      **전에** 뽑아내고, 프로즈만 조건 요약한 뒤 코드는 `render_code_slide_html()`/
      `render_mermaid_slide_html()`로 원문 그대로 별도 슬라이드에 붙인다 —
      둘 다 LLM을 호출하지 않는다(환각 위험 없음, 문자열 조립일 뿐).
    - **Q(렌더링 자산 미로드)**: `html_builder.py`(도서)는 CDN으로
      mermaid.js/highlight.js를 로드하는데 `slide_builder.py`는 reveal.js
      코어만 로드했다 — 코드/다이어그램이 슬라이드에 살아남아도 렌더링될
      수 없었다. `html_builder.py`와 정확히 같은 CDN URL·버전
      (`mermaid@10`, `highlight.js@11.9.0`)과 초기화 방식을 맞췄다 — 도서와
      발표자료가 같은 소스에서 나온 코드/다이어그램을 다르게 렌더링할
      이유가 없다.
    - **R(빈 슬라이드 버그)**: `split_chapter_into_sections()`는 `# `/`## `
      헤딩이 하나도 없으면 섹션을 하나도 못 찾는다. 실측 재현: diagram
      content_type 챕터가 헤딩 없이 ` ```mermaid `로 바로 시작하자(LLM이
      "# Chapter N:"으로 시작하라는 프롬프트 지시를 이번엔 안 지킴)
      슬라이드가 조용히 0장 생성됐다 — 에러 없이 낮은 가시성의 경고
      한 줄(`generate_report() called with no recorded tasks`)만 남았다.
      `fallback_heading` 파라미터를 추가해, 헤딩이 전혀 없어도 본문이
      있으면 챕터 제목을 헤딩 삼아 최소 1개 섹션은 만들도록 고쳤다.
    - `tests/test_slide_builder.py`에 12개 테스트 추가 — 세 결함 각각의
      단위 테스트 + 종단 테스트(`test_build_slides_preserves_code_blocks_verbatim`,
      `test_build_slides_diagram_only_chapter_produces_at_least_one_slide`).
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경): exercise
      타입 챕터(`import unittest`로 시작하는 실제 코드 포함)로 슬라이드를
      만드니 그 코드가 `<pre><code class="language-python">`에 원문 그대로
      나타났고, `highlight.min.js`/`mermaid.min.js` 둘 다 로드됐다.
    - **S/U(같은 조사에서 발견, 아직 미구현)**: 기획/목차 설계가 코드
      구조를 전혀 못 보는 것(S), 다이어그램이 H의 정확한 의존 관계 데이터를
      활용 안 하는 것(U) — SPEC.md 2부에 문제/해법/우선순위 기록. T(전체
      커버리지 미보장)는 항목 32에서 이어서 구현.

32. **`module_reference` content_type(일반 능력 T, SPEC.md 2부)을 추가해,
    RAG 유사도에 좌우되던 "전체를 다룬다" 문제를 고쳤다.** 항목 31과 같은
    조사(Book-forge 자신의 agents/ 13개 파일을 실제로 분석)에서 발견 —
    `reference_table`은 top-k RAG 검색으로 뽑힌 것만 표에 담기 때문에,
    실측: agents 13개 파일 중 우연히 4개만 다뤄지고 나머지 9개는 왜
    빠졌는지 아무 신호도 없이 조용히 사라졌다.
    - `agents/module_reference.py::build_generate_module_reference()` —
      `reference_table.py`와 같은 패턴(rag_mode=True, LLM이 값을 지어내지
      않게 지시)이지만, LLM에게 넘기는 `sources`가 RAG 청크가 아니라
      H(`build_structure_index`+`format_structure_summary`, 새 파싱 로직
      없이 기존 인프라 재사용)가 만든 **결정론적 전체 목록**이다 — "어떤
      항목이 존재하는가"는 코드가 이미 정했고, LLM은 각 항목의 설명 문구만
      채운다.
    - `draft_cmd.py::_build_module_reference_summary(sources)` — `--source`
      중 로컬 디렉토리인 것만 골라 H로 정적 분석한다. 디렉토리 소스가
      하나도 없으면(PDF/URL만 준 경우) `None`을 반환하고, 호출부가 일반
      RAG 소스로 조용히 대체한다(에러로 막지 않음 — module_reference를
      골랐다는 이유만으로 실패시킬 이유는 없음, 대신 "전체 커버리지 보장
      안 됨"을 경고).
    - **`effective_sources_text`로 통일**: `_draft_one_chapter()`가
      module_reference일 때만 `sources_text`(RAG 청크)를 구조 요약으로
      바꿔치기하고, 생성 호출과 사후 검증(`_print_verification`) 양쪽에
      같은 값을 쓰도록 통일했다 — 다른 content_type은 기존 RAG 청크
      그대로라 회귀가 없다.
    - `agents/demonstration_verifier.py::verify_module_reference_coverage()` —
      구조 요약에서 뽑은 클래스/함수 이름이 전부 본문에 등장하는지 확인한다
      (`verify_reference_table()`의 "값을 지어내지 않았는가"와 반대 방향 —
      여기서는 "빠뜨리지 않았는가"). **구현 중 발견한 버그**: 이름 추출
      정규식에 `re.MULTILINE`을 빼먹어서 항상 빈 목록만 매치됐다 — "이름이
      없으면 통과"라는 폴백 때문에 실패 테스트를 짜기 전까지는 통과
      테스트가 (엉뚱한 이유로) 계속 초록불이었다. 실패 시나리오
      테스트(`test_verify_module_reference_coverage_fails_when_names_missing`)를
      쓰고 나서야 잡혔다 — "통과하는 테스트 하나"보다 "의도한 이유로
      통과/실패하는 테스트 쌍"이 왜 중요한지 보여주는 사례.
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경, 항목 31과
      같은 `agents/` 디렉토리로 재현): 44개 항목(클래스+함수)을 전부
      결정론적으로 나열했고, 실제 생성된 표에는 28개가 담겼다 — 나머지
      16개(주로 `build_*`/`parse_*` 팩토리 함수)는 CLI에 `` `이름`이(가)
      본문에 없습니다 `` 형태로 정확히 무엇이 빠졌는지 보고됐다. 이전엔
      "13개 중 4개, 이유 불명"이었던 것이 "44개 항목을 전부 알고 있고,
      그중 몇 개가 왜 빠졌는지도 안다"로 바뀐 것 — LLM이 표를 100% 채우는
      것까지 보장하진 않지만(그건 이 항목의 목표가 아니었음), 최소한
      "무엇이 빠졌는지 조용히 모르는" 상태에서는 벗어났다.

33. **diagram content_type이 H의 구조 요약을 활용하도록 확장하고,
    `verify_diagram()`에 그라운딩 체크를 추가했다(일반 능력 U, SPEC.md
    2부).** 항목 31/32와 같은 조사에서 발견 — 다이어그램은 100% LLM이
    RAG 텍스트 조각에서 재구성한 것이라, 실측: "패키지 구조" 다이어그램을
    요청했는데 파일 1개(`planner.py`)의 내부 데코레이터 관계만 그려졌다
    (로컬로는 정확하지만 스코프가 틀림). 기존 검증도 mermaid 문법만 보지,
    실제 코드 관계와 일치하는지는 확인 안 했다.
    - **T의 헬퍼를 그대로 재사용**: 처음엔 "코드로 노드/엣지를 직접
      조립"까지 고려했으나, T가 이미 만든
      `_build_structure_summary_from_sources()`(H의 구조 요약, "내부
      의존:"/"외부 의존:" 표기 포함)를 diagram content_type에도 그대로
      적용하는 게 더 간단하고 T와 일관됐다 — 함수 이름을
      `_build_module_reference_summary`에서 `_build_structure_summary_from_sources`로
      리네이밍해 T/U 공유 헬퍼임을 드러냈다. `effective_sources_text`
      오버라이드 조건을 `content_type in ("module_reference", "diagram")`로
      확장한 게 전부다 — 새 파이프라인이 아니라 기존 T 배선의 자연스러운
      확장.
    - `agents/diagram_generator.py::DIAGRAM_PROMPT`에 "소스에 '내부
      의존:'/'외부 의존:' 표기가 있으면 그 관계를 노드/엣지로 그대로
      옮기라"는 지시를 추가했다 — 그래프 구조를 LLM이 처음부터
      창작하지 말고, 있으면 정적 분석 결과를 우선 반영하게 유도.
    - `agents/demonstration_verifier.py::verify_diagram()`에 옵트인
      `sources_text` 파라미터를 추가했다(`verify_diagram(draft_md,
      sources_text="")` — 하위 호환, 빈 문자열이면 기존 동작 그대로).
      주어지면 그래프 노드 라벨(`\[...\]`)에서 뽑은 식별자가 소스에 실제로
      등장하는 비율을 확인한다 — `verify_reference_table()`의 "값이
      소스에 있는가" 원칙을 다이어그램에도 적용한 것. 이 체크는
      diagram뿐 아니라 기존 RAG 기반 diagram 생성에도 그대로 적용된다
      (sources_text가 RAG 청크든 구조 요약이든 상관없이 동작하는 일반화).
    - `tests/test_demonstration_verifier.py`에 그라운딩 통과/실패/스킵
      3개 테스트를 추가하면서, 대괄호 없는 노드(`PlannerAgent --> ChatAgent`)
      로 처음 짰다가 `_MERMAID_NODE_LABEL_RE`가 대괄호 라벨(`A[PlannerAgent]`)
      만 인식한다는 걸 깨닫고 실제 LLM 출력과 같은 문법으로 고쳐 썼다 —
      고치기 전엔 node_labels가 항상 빈 리스트라 그라운딩 검사 자체가
      조용히 스킵되는, 항목 32와 같은 유형의 "의도와 다른 이유로 통과하는
      테스트" 함정이었다(수동으로 `_MERMAID_NODE_LABEL_RE.findall()`을
      돌려 실제로 식별자가 뽑히는지 확인하고 나서야 안심했다).
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경, 항목 31/32와
      같은 `agents/` 디렉토리로 재현): "agents 패키지의 모듈 의존 관계"
      다이어그램을 요청하니, 19개 파일 전체를 아우르는 모듈 의존 그래프가
      나왔다 — 각 파일의 실제 import 문(예: `code_consistency_checker.py`
      → `pkgutil`/`importlib`)과 정확히 일치했다. 이전엔 파일 1개짜리
      스코프 불일치였던 것이 패키지 전체 스코프로 바뀐 것이 U의 실질적
      성과.

34. **`book-forge new --source`가 목차 설계 *이전*에 코드 구조를 미리
    분석하도록 고쳤다(일반 능력 S, SPEC.md 2부) — 항목 31~33과 같은
    조사에서 발견한 가장 근본적인 격차.** `propose_plan()`/`design_toc()`는
    저자가 타이핑한 자유 텍스트만 보고, `--source`는 목차 확정 **이후**
    draft 단계에서만 쓰였다 — 실측: "Book-forge의 agents 패키지 구조를
    분석"이라는 제약을 줘도 실제로 존재하지 않는 "에이전트 컴포넌트 간
    상호작용 및 통신 메커니즘" 같은 챕터가 만들어졌다. H가 이미 정확한
    모듈 인벤토리를 갖고 있는데도 기획/목차 단계에 전혀 연결돼 있지
    않았던 게 원인.
    - `agents/prompts.py::_CODE_STRUCTURE_BLOCK` — TOC_PROMPT에 `{code_structure_block}`
      플레이스홀더를 추가하고, 빈 문자열이면 자연스럽게 접히도록(추가
      공백 한 줄 외엔 흔적 없음) 별도 블록 상수로 분리했다 — 프롬프트
      두 벌을 만들지 않기 위함.
    - `agents/toc_designer.py::design_toc()`에 옵트인 `code_structure: str = ""`
      파라미터를 추가했다 — 주어지면 `_CODE_STRUCTURE_BLOCK`을 채워 넣고,
      비어 있으면(기존 호출부, PDF/URL 소스, `--source` 자체가 없는 경우)
      기존 프롬프트와 완전히 동일하게 동작한다(하위 호환).
    - `cli/commands/new_cmd.py` — `--source`가 있으면 `llm`/`monitor`
      준비 직후, **기획안 생성보다도 먼저** `_build_structure_summary_from_sources()`
      (T/U가 이미 만든 헬퍼, 항목 32 재사용)를 호출해 `code_structure`를
      계산한다. 순수 AST 정적 분석이라 임베딩·LLM 호출 없이 빠르다 —
      지식창고에 소스를 청크·임베딩하는 무거운 작업(스캐폴딩 이후 자동
      배치 초안 단계)과는 완전히 별개 경로다.
    - `tests/test_toc_designer.py`(신규) + `tests/test_new_cmd.py`에 구조
      요약 유무에 따라 TOC 프롬프트 내용이 달라지는지 확인하는 테스트를
      추가했다 — `RecordingLLM`으로 실제 프롬프트 문자열을 캡처해 대조.
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경, 항목 31~33과
      같은 시나리오 — "Book-forge 아키텍처 해설", `--source`를 `new`
      시점부터 지정): 목차가 "Chapter 5. 챕터 초안 작성자
      (chapter_drafter.py)", "Chapter 7. 코드 일관성 검증기
      (code_consistency_checker.py)"처럼 **실제 파일명을 챕터 제목에 직접
      인용**하는 수준으로 바뀌었다 — 이전 실측에서 나왔던 존재하지 않는
      서브시스템("컴포넌트 간 통신 메커니즘" 등)이 완전히 사라졌다. 이후
      `--source`가 트리거하는 전체 챕터 자동 배치 초안(12개 챕터)까지
      돌리다 5분 foreground 타임아웃에 걸렸지만, 목차 자체는 이미
      완성된 뒤였고 그게 이 항목이 검증하려던 것이었다.

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

35. **`book-forge new`가 슬러그 충돌 시 확인 없이 기존 기획안/목차를
    덮어쓰던 문제를 고쳤다(일반 능력 AH, SPEC.md 4부).** "주제 입력 →
    소스 수집 → ... → Config 관리 → 최종 선정" 전 과정을 분석해달라는
    요청 중 발견 — `ensure_project_dir()`이 `mkdir(exist_ok=True)`만 써서,
    같은 제목으로 `book-forge new`를 두 번 실행하면 `00_기획안.md`/
    `01_목차.md`가 경고 없이 새로 써졌다.
    - `new_cmd.py`에서 `ensure_project_dir()`(디렉토리를 실제로 만듦) 호출
      **전에**, `00_기획안.md` 존재 여부만 확인해 있으면
      `click.confirm(..., default=False)`로 확인을 받는다. 거부하면
      `SystemExit(0)`(에러가 아니라 저자가 선택한 정상 취소 — 다른
      cancel 경로들과 같은 관례). `--force` 플래그로 확인을 건너뛸 수
      있다(`draft`의 `--force`와 같은 이름 재사용, 자동화/스크립트용).
    - **구현 중 발견한 진짜 함정**: 처음엔 `new_cmd.py`가
      `from book_forge.config import get_data_dir`로 직접 import해서 썼는데,
      기존 테스트가 `monkeypatch.setattr(config_module, "get_data_dir", ...)`로
      **`config.py` 모듈의 속성**을 패치하는 방식이라, `new_cmd.py`가 이미
      import 시점에 스냅샷해둔 별도 바인딩에는 그 패치가 반영되지 않는다
      (Python의 `from X import Y`는 실시간 참조가 아니라 그 시점의 값
      복사). `ensure_project_dir()`는 이 문제가 없었던 이유는 함수 본문이
      `config.py` **자기 자신의** 전역 네임스페이스에서 `get_data_dir`을
      찾기 때문 — 어느 모듈이 `ensure_project_dir`을 import해서 쓰든
      상관없이 항상 최신 패치를 본다. 이 차이를 이용해 `config.py`에
      `project_dir_for(slug)`(디렉토리를 안 만들고 경로만 계산) 헬퍼를
      추가하고 `new_cmd.py`가 그걸 쓰도록 해서 우회했다 — 새 로직이
      아니라 기존 함정을 피해가는 배선 문제였다.
    - 실측(실제 Ollama, `qwen3-coder:latest`, `/tmp` 격리 환경): 같은
      제목으로 두 번째 `new`를 실행하니 "이미 존재하는 프로젝트입니다"
      확인 프롬프트가 뜨고, 콘솔에서 `n`을 입력하니 기존 기획안이 그대로
      보존됐다.

36. **`book-forge gate`가 책 전체가 아니라 챕터 하나만 판정하던 문제를
    고쳤다(일반 능력 AF, SPEC.md 4부) — 이 파이프라인 분석에서 나온 가장
    심각한 발견.** `draft_cmd.py::_draft_one_chapter()`가 챕터마다 새
    `PerformanceMonitor`를 만들어 `draft_ch{N}.json`으로 따로 저장한다 —
    책 전체를 누적하는 프로젝트 단위 모니터가 없었다. `gate_cmd.py`의
    옛 `_latest_result_file()`은 `--file` 없이 부르면 mtime 기준 가장
    최근 파일 하나만 골랐다.
    - **실측 재현(고치기 전)**: 실제 6챕터 프로젝트(`AI_에이전트_평가_입문`)에서
      `book-forge gate "AI_에이전트_평가_입문" --min-gate-score 0.0`을
      실행하니 `draft_ch05.json` 하나만 게이팅됐다 — Chapter 1/2/3/4/6은
      완전히 무시됐다(그 시점에 마지막으로 재생성한 챕터가 5였을 뿐인데도).
    - **agent-evaluator에 이미 있는 병합 기능을 처음 실제로 썼다**: 별도
      조사로 `PerformanceMonitor.merge()`/`.load_from_file()`가
      `core/trackers/monitor.py`에 이미 있고(D8), `agent-eval gate` CLI
      자체는 파일 하나만 받는 구조라는 걸 확인했다. `merge()`는
      `self.merge(other)`가 `self`의 설정을 기준으로 한 **새 인스턴스**를
      반환하는 순수 함수형 API라, N개 파일을 fold로 접었다:
      `merged = load_from_file(files[0]); for f in files[1:]: merged =
      merged.merge(load_from_file(f))`.
    - `gate_cmd.py::_all_result_files(eval_dir)` — `eval_results/*.json`
      전부를 모으되 `baseline.json`(`--save-baseline`이 만드는 비교
      기준, 리포트가 아님)과 자기 자신이 만드는
      `_merged_gate_result.json`은 제외한다 — 후자를 안 걸러내면 다음
      `gate` 실행 때 이전 병합 결과가 또 병합 입력으로 들어가는 피드백
      루프가 생긴다(구현하면서 바로 알아채고 처음부터 제외 목록에 넣음).
    - **계획과 살짝 다르게 구현**: SPEC에 적을 때는 `--all` 플래그를
      제안했지만, 실제로는 `--file` 없이 부르는 **기본 동작 자체**를
      바꿨다 — 파일이 1개뿐이면(대부분의 초기/소규모 프로젝트) 병합 왕복
      없이 그 파일을 그대로 쓰므로 기존 단일-챕터 프로젝트의 동작과
      완전히 동일하다(하위 호환 깨짐 없음, `tests/test_gate_cmd.py`의
      기존 5개 테스트가 코드 변경 없이 그대로 통과함으로 확인). `--file`을
      명시하면 여전히 특정 챕터 하나만 다시 보고 싶을 때 쓸 수 있다.
    - `tests/test_gate_cmd.py`에 4개 테스트 추가 — 6챕터 집계
      (`total_tasks == 6`), baseline/이전 병합본 제외 확인(두 번 연속
      실행해도 입력 파일 수가 안 늘어남), 단일 파일일 때 기존 동작
      그대로임을 명시적으로 고정.
    - 실측(실제 `AI_에이전트_평가_입문` 프로젝트 — 이 문제를 원래 발견한
      바로 그 프로젝트): 수정 후 `book-forge gate`가 7개 파일(챕터 6개 +
      `planning.json`)을 자동으로 집계해 `_merged_gate_result.json` 하나로
      게이팅했다. 두 번 연속 실행해도 매번 정확히 같은 7개 파일만
      입력으로 잡혀 피드백 루프가 없음을 확인했다. 집계된 Gate 점수(A
      0.286 fail, D 0.164 fail, G 0.000 fail)는 어떤 단일 챕터의 점수와도
      다르게 나왔다 — 개별 챕터 시점에는 안 보이던, 책 전체 수준에서만
      드러나는 문제가 실제로 있었다는 뜻이라 AF가 해결하려던 문제가
      허구가 아니었음을 다시 한번 확인해준다.

37. **표지·저작권·저자 정보(front matter)를 처음으로 추가했다(일반 능력
    AI, SPEC.md 4부).** "출판 가능한 기술 서적" 수준에 필요한 기능을
    분석해달라는 요청 중 발견 — `BookConfig`는 `title`/`accent_color`
    두 필드뿐이었고, `html_builder.py`/`pdf_builder.py`/`PLAN_PROMPT`
    어디에도 저자/저작권/판 개념이 없었다(`grep` 0건 확인).
    - **저자명을 `00_기획안.md`에 안 끼워 넣은 이유**: 그 파일은
      `PlannerAgent`가 생성하는 순수 프로즈(`## 목적`으로 시작)에
      `new_cmd.py`가 저장 시점에 `# {title}\n\n` 접두어만 붙인다는
      계약이 이미 있고, `plan_cmd.py::_strip_title_h1()`이 정확히 이
      형식을 가정해 접두어를 벗겨낸 뒤 리뷰 루프에 다시 넣는다. 저자명
      한 줄을 그 사이에 끼워 넣으면 이 계약이 깨진다 — 완전히 별도
      파일(`publish/front_matter.py`의 `front_matter.json`)로 분리해
      기존 파싱/리뷰 로직을 전혀 안 건드렸다.
    - `FrontMatter`(author/license_notice/edition, 전부 기본값 빈
      문자열) + `load_front_matter()`/`save_front_matter()` — 전부
      빈 값이면 파일 자체를 안 만든다(`is_empty` 가드, 기존 프로젝트에
      영향 없음). `new_cmd.py`에 `--author`/`--license-notice`/`--edition`
      옵션을 추가했다 — **LLM을 호출하지 않는다**, 저자가 입력한 값을
      그대로 저장할 뿐이라 창작 대상이 아니다(환각 위험 자체가 없음).
    - `project_utils.py::load_book_config()`가 front_matter.json을 읽어
      `BookConfig`에 채워 넣는다. `html_builder.py::build_title_page()`가
      제목+저자+판+저작권 고지를 `<section class="title-page">`로
      조립한다(순수 문자열 조립, 전부 `html.escape` 처리). `<main>` 맨
      앞, 첫 챕터 섹션 바로 앞에 삽입.
    - **PDF는 챕터별 개별 파일 구조라 "표지"도 같은 패턴**: `pdf_builder.py`가
      `html_builder.py`의 `build_title_page()`/`_standalone_chapter_html()`을
      재사용해 `00_표지.pdf`라는 별도 파일을 챕터 PDF들보다 먼저 생성한다
      (`chapter_no` 지정한 단일 챕터 재생성 모드에서는 표지를 다시 안
      만든다 — 매번 헷갈리지 않게).
    - **구현 중 또 발견한 같은 종류의 함정(항목 35와 동일 패턴)**:
      `test_project_utils.py`의 새 테스트를 처음엔
      `monkeypatch.setattr(config_module, "get_data_dir", ...)`로 짰다가
      실패했다 — `project_utils.py::resolve_project_dir()`은 `config.py`가
      아니라 **`project_utils.py` 자기 자신**에 import된 `get_data_dir`
      바인딩을 쓰므로, 패치 대상도 `project_utils.get_data_dir`이어야
      한다(기존 `test_gate_cmd.py`/`test_draft_cmd.py`가 이미 이 패턴을
      쓰고 있었는데 새로 테스트를 짤 때 놓쳤다). **일반화된 교훈**: 이
      프로젝트에서 `from X import get_data_dir`로 가져온 함수를 호출하는
      코드를 테스트할 때는, 그 함수가 **정의된 모듈**이 아니라 **그
      함수를 import해서 실제로 호출하는 모듈**의 네임스페이스를
      패치해야 한다 — 이미 두 번(항목 35, 이번) 같은 함정에 걸렸다.
    - 실측(실제 Ollama, 실제 Playwright, `/tmp` 격리 환경): `--author
      김성우 --license-notice "..." --edition "1판 1쇄"`로 프로젝트를
      만들고 HTML/PDF를 둘 다 빌드해, HTML에는 표지 섹션이 올바른 값
      그대로 렌더링됐고 PDF에는 `00_표지.pdf`(46KB, 실제 내용 있음)가
      챕터 PDF들보다 먼저 만들어짐을 확인했다.

38. **agent-evaluator Config가 전부 하드코딩돼 있던 문제를 고쳤다(일반
    능력 AG, SPEC.md 4부).** 데이터 수집→주제 입력→Config 관리→최종
    판정까지 전 과정을 분석해달라는 요청 중 발견 — `LLMJudgeConfig` 계열
    파라미터가 CLI 어디에도 노출돼 있지 않았고(플래그는 이미 존재하되
    `build_book_monitor()`까지 실제로 이어지지 않음), Gate 가중치
    (`gate_a_tcr_weight` 등)도 `PerformanceMonitor` 기본값 그대로 고정돼
    있었다.
    - **범위를 의도적으로 좁혔다**: 33개 Harness Config 전부를 CLI/설정
      파일로 노출하는 대신, SPEC.md 자체가 제시한 두 선택지 중 더 단순한
      쪽만 구현했다 — `new`/`draft`에 `--enable-llm-judge`/`--judge-model`
      옵트인 플래그를 배선하고, Gate 가중치 3종(`gate_a_tcr_weight`/
      `gate_c_tcr_weight`/`gate_b_loop_weight` — agent-evaluator가 이미
      지원, 위 아키텍처 섹션에 문서화됨)만 `.env` 환경변수로 노출했다.
      `book_forge_config.toml` 같은 새 설정 파일 형식은 만들지 않았다 —
      LLM Provider 선택이 이미 `.env`를 쓰고 있어 같은 메커니즘을 재사용하는
      편이 새 형식을 하나 더 배우게 하는 것보다 나았다.
    - `eval/monitor.py`에 `_GATE_WEIGHT_ENV_VARS`(env 이름→kwarg 이름
      매핑 3쌍) + `_gate_weight_overrides()`(미지정 시 건너뜀, 파싱 실패
      시 조용히 무시 — 이 프로젝트의 "관대한 파싱" 관례와 동일)를 추가하고,
      `build_book_monitor()`가 `**_gate_weight_overrides()`로
      `PerformanceMonitor`에 전달한다. `new_cmd.py`/`draft_cmd.py`
      모두에 `enable_llm_judge`/`judge_model` 파라미터를 관통시켜(이미
      이번 세션에서 `sources`/`max_per_source`에 썼던 것과 동일한 스레딩
      패턴) `build_book_monitor()` 호출까지 실제로 이어지게 했다 — 새
      판정 로직은 없다, 이미 존재하던 파라미터를 실제로 연결한 것뿐.
    - **실측 범위가 두 갈래로 갈린 이유**: agent-evaluator의 `LLMJudge`가
      OpenAI/Anthropic 모델만 지원하고 Ollama 연동이 전혀 없음을
      `grep -n "ollama\|Ollama" llm_judge.py` 0건으로 확인했다 — 실제
      채점 호출을 검증하려면 유료 API 키가 필요해, 명시적 허락 없이
      비용을 쓰지 않기로 하고 오프라인 스파이 테스트(플래그가
      `build_book_monitor()`까지 정확히 전달되는지)로만 검증했다. Gate
      가중치 오버라이드는 API 키가 필요 없어, 실제 `.env` 파일(
      `BOOK_FORGE_GATE_A_TCR_WEIGHT=0.9`) → 실제 `load_config()`(HOME
      오버라이드한 격리 환경) → `os.environ` → `PerformanceMonitor`
      전체 경로를 몽키패치 없이 직접 실행해 `_gate_a_tcr_weight == 0.9`
      로 반영됨을 확인했다.

39. **챕터 간 기술 용어 표기 불일치를 찾아 보고하는 `book-forge lint`를
    추가했다(일반 능력 AK, SPEC.md 4부).** 각 챕터가 독립된 LLM 호출 +
    독립된 RAG 컨텍스트로 생성되므로 같은 대상을 챕터마다 다르게 표기할
    구조적 위험이 있다는 점을 이 세션 중 배치 재생성에서 실제로 관찰한
    적이 있다.
    - **범위를 SPEC이 명시한 대로 의도적으로 좁혔다**: 전체 도서 대상의
      NLP 기반 동의어 탐지(예: "Gate" vs "게이트" 같은 한영 개념 매칭)는
      과설계 위험이 커서 제외했다. 대신 `code_consistency_checker.py`가
      이미 갖고 있던 `_BACKTICK_RE`(백틱 식별자 추출)/`_BUILTIN_EXCLUSIONS`
      (None/True 같은 표준 어휘 제외 목록)를 그대로 재사용해(새 정규식을
      또 안 만듦), 대소문자·구두점을 지운 "접힌 키"가 같은데 실제 표기가
      다른 경우만 후보로 잡는다 — `ToolCallAnalyzer` vs
      `tool_call_analyzer` vs `Tool-Call-Analyzer`처럼 순수하게 구조적으로
      판정 가능한 변형만 다룬다.
    - 새 모듈 `agents/term_consistency_checker.py`: `find_term_variants()`가
      (챕터 라벨, 본문) 쌍 목록을 받아 `TermVariantGroup`(접힌 키 + 표기별
      등장 챕터 목록) 리스트를 반환한다 — 표기가 하나뿐인(이미 일관된)
      용어는 결과에서 제외한다.
    - 새 명령 `cli/commands/lint_cmd.py`: `book-forge lint <slug>`가
      `load_toc()`로 전체 챕터 본문을 모아 위 함수를 호출하고, 후보
      목록을 표기별 등장 챕터와 함께 출력한다. **자동으로 통일하지
      않는다** — LLM이 직접 고치지 않고 저자에게 후보만 보여준다는 SPEC의
      원칙 그대로. CI 연동이 필요할 수 있어 `--fail-on-gate-warn` 같은
      기존 opt-in 실패 플래그 관례를 따라 `--fail-on-inconsistency`
      (지정 시 후보가 하나라도 있으면 exit 1)만 추가했다 — 기본값은
      항상 exit 0(보고만, 게이팅 아님).
    - 실측(실제 `~/Documents/BookForge/projects/AI_에이전트_평가_입문`,
      이 세션에서 AF 검증에도 썼던 실제 6챕터 프로젝트, 읽기 전용이라
      부작용 없음): `generate_report`(Chapter 3) vs `_generate_report`
      (Chapter 5), `Settings` vs `_settings`(둘 다 Chapter 3 안에서도
      혼용) 두 건의 실제 표기 불일치를 찾아냈다 — LLM이 이미 실제로
      만들어낸 드리프트를 사후에 잡아내는 첫 실증 사례.

40. **책 끝 찾아보기(색인)를 자동 생성하는 `--with-index`를 HTML/PDF
    빌드에 추가했다(일반 능력 AL, SPEC.md 4부).** 실제 기술 서적은 거의
    항상 키워드→위치 찾아보기가 끝에 있는데, `grep`으로 "찾아보기"/
    "색인"/"index"를 검색해도 소스 어디에도 없었다.
    - **새 추출 규칙을 또 안 만들었다**: AK(항목 39)가 이미 검증해둔
      `term_consistency_checker._extract_terms()`(백틱 식별자 추출 +
      builtin 제외 + 최소 길이 필터)를 그대로 재사용한다. 새 모듈
      `publish/book_index.py::build_index_entries(chapters)`가 챕터
      본문을 읽어 용어별로 등장 챕터 목록을 모으고(가나다/알파벳 순
      정렬), `html_builder.py::build_index_section()`이 그 결과를
      `<dl>` 목록으로 렌더링한다.
    - **PDF와 HTML의 "위치" 표현이 의도적으로 다르다**: SPEC 원문이
      "챕터 제목→(가능하면 페이지 번호) 매핑... HTML은 페이지 개념이
      없으므로 챕터 링크로 대체"라고 했는데, 실제로는 PDF도 챕터별
      개별 파일 구조(표지·`.venv` 관련 이전 항목들과 동일 제약)라 파일을
      가로지르는 진짜 페이지 번호 자체가 존재할 수 없다. 그래서
      `build_index_section(entries, with_links=True|False)`로 한
      함수를 공유하되: HTML(단일 파일)은 실제 `href="#chNN"` 앵커 링크,
      PDF(챕터별 별도 파일)는 다른 파일을 가리키는 죽은 링크를 만들지
      않도록 챕터 번호/제목 텍스트만 표기한다 — SPEC의 "가능하면"이라는
      단서를 아키텍처 제약 안에서 정직하게 절충한 것.
    - `book-forge build html --with-index`/`build pdf --with-index`
      옵트인 플래그(기본 off, SPEC이 "옵트인 단계"라고 명시) — PDF는
      AI의 표지(`00_표지.pdf`)와 같은 패턴으로 `99_찾아보기.pdf`를
      챕터별 PDF 뒤에 별도 파일로 추가한다(`chapter_no` 지정한 단일
      챕터 재생성 모드에서는 표지와 마찬가지로 안 만든다). 옵트인으로
      둔 이유: 매 빌드마다 전체 챕터를 다시 읽어 용어를 재추출하는
      추가 비용이 있고, 초안이 자주 바뀌는 동안은 색인도 자주 바뀌어
      의미가 적다.
    - 실측(실제 `AI_에이전트_평가_입문`, 6챕터, HTML은 원본 백업 후
      복원해 부작용 없음, PDF는 기존에 없던 `outputs/pdf/` 디렉토리를
      새로 만드는 순수 추가 산출물이라 원복 불필요): HTML은
      `__repr__`/`_chunk_text`/`_generate_report` 등 실제 코드
      식별자로 색인이 채워졌고 `href="#ch03"` 앵커가 실제 Chapter 3
      섹션을 정확히 가리켰다. PDF는 78KB `99_찾아보기.pdf`가 6개 챕터
      PDF 뒤 7번째 파일로 정상 생성됐다.

41. **EPUB 3 출력을 추가했다(일반 능력 AJ, SPEC.md 4부, 명시적으로
    우선순위 낮음으로 분류돼 있던 마지막 항목).** Book-forge는 HTML/PDF/
    Slides만 만들었는데, 실제 전자책 유통(Amazon KDP, 교보문고 e-book 등)
    채널은 대부분 EPUB을 요구한다.
    - 새 `publish/epub_builder.py`: SPEC이 명시한 대로 `zipfile` 표준
      라이브러리만으로 EPUB 3 컨테이너(mimetype 비압축 첫 항목 +
      `META-INF/container.xml` + `OEBPS/content.opf` + `OEBPS/nav.xhtml` +
      챕터별 XHTML)를 조립한다 — Playwright 같은 브라우저 의존성이 전혀
      없다(PDF와 다른 지점, SPEC이 이미 이 차이를 명시했었음).
      `md_to_html()`(HTML/PDF와 동일 변환 엔진)을 그대로 재사용한다.
    - **이미지 처리가 HTML과 다른 이유**: HTML은 `embed_images_as_data_uri()`로
      base64 인라인해 "파일 하나로 이메일 첨부/이동"이 되게 하지만, EPUB은
      컨테이너 자체가 이미 "여러 파일을 담는 zip"이라 실제 파일로 넣는
      쪽이 표준이다(SPEC 원문이 명시). `markdown_engine.py`에
      `rewrite_images_for_epub()`을 새로 추가해(`embed_images_as_data_uri()`의
      짝) img src를 `images/<챕터id>_<원본파일명>`으로 재작성하고 실제
      파일 목록을 반환한다 — 챕터id 접두어를 붙인 이유는 서로 다른 챕터
      디렉토리의 동일 파일명(`images/diagram.png` 등)이 EPUB의 단일
      `images/` 폴더에서 충돌하지 않게 하기 위함.
    - `guess_image_media_type()`을 `markdown_engine.py`에 새로 뽑아
      `embed_images_as_data_uri()`(기존)와 EPUB manifest의 media-type
      계산이 같은 MIME 판정 로직(`_IMG_MIME_OVERRIDES` + `mimetypes`)을
      공유하게 리팩터링했다 — 로직 중복 없음.
    - **계획에 없던 안전장치를 하나 추가했다**: mermaid/`@@HTML_START@@`
      커스텀 HTML 블록은 HTML/PDF와 마찬가지로 escape 없이 원문 그대로
      삽입되는데, EPUB 리더가 요구하는 XML 파서는 브라우저의 관대한 HTML
      파서보다 훨씬 엄격해 짝이 안 맞는 태그 하나가 EPUB 파일 전체를 못
      열게 만들 수 있다. `_well_formed_chapter_xhtml()`이
      `xml.etree.ElementTree.fromstring()`으로 조립된 챕터 XHTML을
      검증해, 실패하면 그 챕터만 escape된 원문 텍스트(`<pre>`)로 안전하게
      대체한다 — 다른 챕터/EPUB 전체는 영향받지 않는다. 새 테스트
      (`test_build_epub_recovers_from_malformed_raw_html_block`)로 실제
      짝 안 맞는 태그를 넣어 이 폴백 경로를 직접 확인했다.
    - **알려진 한계로 명시**: EPUB 리더 대부분은 리플로우 가능한 콘텐츠에서
      JavaScript를 실행하지 않으므로(보안/UX 정책) mermaid.js CDN
      스크립트를 애초에 EPUB XHTML head에 넣지 않았고, mermaid 다이어그램은
      렌더링되지 않은 원본 그래프 정의 텍스트로 보인다 — PDF의 Mermaid
      청크 잘림 한계와 같은 급의 후속 개선 과제.
    - `book-forge build epub <slug>` 명령 추가(`BookConfig.epub_output_path`
      프로퍼티 신설, 다른 산출물과 동일한 `outputs/<slug>.epub` 패턴).
    - 실측(실제 `AI_에이전트_평가_입문`, 6챕터): 48KB EPUB 생성 확인,
      `zipfile.testzip()` 무결성 통과, mimetype이 비압축 첫 항목임을 확인,
      `content.opf`/`nav.xhtml`/챕터 6개 XHTML 전부 `ET.fromstring()`으로
      well-formed XML 파싱 성공을 확인했다. `epubcheck`(공식 검증 도구)는
      이 환경에 설치돼 있지 않아 돌리지 못했다 — zip 무결성 + 전체 XML
      well-formedness는 "EPUB이 열리기라도 하는지"의 핵심 조건이라 이
      단계에서는 충분한 신호로 판단했고, 실제 전자책 채널 제출 전에는
      `epubcheck`로 별도 검증을 권장한다(README에 명시).

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
- **`get_data_dir` 같은 함수를 `monkeypatch.setattr`로 패치할 땐, 그 함수가
  "정의된" 모듈이 아니라 그 함수를 import해서 "실제로 호출하는" 모듈의
  네임스페이스를 패치해야 한다** — `from X import Y`는 실시간 참조가 아니라
  import 시점의 값 복사라, `X.Y`를 나중에 패치해도 이미 `from X import Y`로
  가져다 쓴 다른 모듈의 바인딩에는 반영되지 않는다. 예: `project_utils.py`가
  `from book_forge.config import get_data_dir`로 가져와 쓰면
  `monkeypatch.setattr(project_utils, "get_data_dir", ...)`로 패치해야지,
  `monkeypatch.setattr(config_module, "get_data_dir", ...)`는 안 먹힌다.
  단, 함수가 **자기 자신을 정의한 모듈 안에서** 다른 함수를 호출하는
  경우(예: `config.py::ensure_project_dir()`이 같은 파일의
  `get_data_dir()`을 호출)는 그 정의 모듈을 패치하면 항상 먹힌다(전역
  네임스페이스 조회가 매번 최신 상태를 보므로) — 이 프로젝트에서 이미
  두 번(항목 35, 37) 같은 함정에 걸렸다가 고쳤다.
