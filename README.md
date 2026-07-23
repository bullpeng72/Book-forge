# Book-forge

AI 협업 다권 도서 저술 파이프라인 — 주제 → 기획안/목차(저자 상호작용) → 마크다운 집필 →
HTML/PDF/발표자료. 전 과정을 [agent-evaluator](https://pypi.org/project/agent-evaluator/)
Gate A–G로 계측·게이팅합니다. LLM Provider는 기본값이 **Ollama(로컬)** — API 키 없이
바로 시작할 수 있습니다.

**핵심 통계**: 10개 에이전트(`@agent_eval`/`@tool_guard` 데코레이터 직접 적용) | CLI 명령
10개(9개 동작) | 140개 테스트 | Python 3.11+

## 목차

- [설치](#설치)
- [사용자 작업 흐름](#사용자-작업-흐름)
- [기능](#기능)
- [일반 능력 A–F (RAG 집필 보조 확장)](#일반-능력-af-rag-집필-보조-확장)
- [CLI 명령](#cli-명령)
- [아키텍처](#아키텍처)
- [Gate A–G 계측](#gate-ag-계측)
- [Book/AOO 마이그레이션](#bookaoo-마이그레이션)
- [알려진 한계](#알려진-한계)
- [개발](#개발)

## 설치

```bash
pip install -e ".[dev]"          # 코어 + 테스트 도구
pip install -e ".[pdf]"          # + Playwright (PDF 빌드용)
pip install -e ".[serve]"        # + Flask (웹 에디터용)
pip install -e ".[rag]"          # + pypdf/numpy (RAG 집필 보조용, Ollama 임베딩 필요)
playwright install chromium      # [pdf] 설치 시 1회

book-forge init                  # LLM Provider 설정 (기본 Ollama — API 키 불필요)
```

OpenAI/Anthropic을 쓰려면 `book-forge init`에서 provider를 선택하거나 `.env`에
`LLM_PROVIDER=openai`(+ `OPENAI_API_KEY`) 또는 `LLM_PROVIDER=anthropic`(+
`ANTHROPIC_API_KEY`)을 설정하세요.

## 사용자 작업 흐름

```
1. 주제 입력
   book-forge new "<제목>" [--constraints "..."]
           │
           ▼
2. 기획안 승인 루프 ── LLM이 초안 생성 → Enter(승인) / 텍스트 입력(수정 요청, 반복)
           │
           ▼
3. 목차 승인 루프 ── Part/Chapter 구조, 같은 승인 방식
           │
           ▼
4. 스캐폴딩 ── Part_X_.../Chapter_XX_....md 빈 파일 자동 생성
           │
           ▼
5. 집필 ── 아래 세 경로 중 선택(섞어 써도 됨. 챕터마다 달라도 무방)
   ┌───────────────┬──────────────────────┬───────────────────────────┐
   │ (a) 직접 작성  │ (b) RAG, 챕터 하나씩  │ (c) RAG, 배치/완전자동     │
   │ 에디터로 편집  │ book-forge draft      │ book-forge draft --all     │
   │ book-forge edit│   <slug> <ch> --source│   <slug> --source ...      │
   │   <slug>       │   ...                 │ 또는 애초에 2번에서        │
   │                │ 낮은 커버리지 시 대안 │ book-forge new --source로  │
   │                │ 제시 + 진행/취소 확인 │ 2~5를 한 번에              │
   └───────────────┴──────────────────────┴───────────────────────────┘
           │
           ▼
6. 산출물 생성
   book-forge build html <slug>      # 단일 자기완결 HTML
   book-forge build pdf <slug>       # 챕터별 PDF
   book-forge build slides <slug>    # 발표자료(Reveal.js)
           │
           ▼
7. 품질 확인
   book-forge gate <slug>            # Gate A-G 종합 판정 (CI 연동 가능)
           │
           ▼
8. 필요하면 반복
   book-forge plan <slug> --revise   # 기획/목차 재조정 (기존 챕터 파일은 보존)
   book-forge draft ... --force      # 특정 챕터만 재생성
   book-forge chat <slug>            # 쌓인 지식창고에 질문하며 보충 자료 확인
```

### 단계별 명령 예시

**1~4. 기획부터 스캐폴딩까지 (필수, 모든 경로 공통)**
```bash
book-forge new "AI 에이전트 평가 입문" --constraints "초보자 대상, 실습 예제 포함"
# → 기획안 표시 → Enter(승인) 또는 피드백 입력 → 재표시 → ... → 승인
# → 목차 표시 → 같은 방식으로 승인
# → Part_X/Chapter_XX.md 스캐폴드 자동 생성
```

**5. 집필 — 상황에 맞는 경로 선택**

| 상황 | 명령 |
|---|---|
| 저자가 모든 내용을 직접 씀 | `book-forge edit <slug>` (웹 에디터, Part/Chapter 트리 + 이미지 갤러리) |
| 특정 챕터 하나만 자료 기반으로 초안이 필요 | `book-forge draft <slug> <chapter_no> --source paper.pdf` |
| 자료가 있는 챕터 전부를 한 번에 채우고 싶음 | `book-forge draft <slug> --all --source ./papers --source ./src --source https://example.com/article` |
| 주제 입력만으로 끝까지 자동으로 밀고 싶음 | `book-forge new "<제목>" --source ./papers` (2~5를 한 번에, 실측 76초/4챕터) |

RAG 경로((b)(c))는 생성 전 소스 커버리지를 점검해 낮으면 경고·대안을 보여줍니다
(단일 모드는 진행/취소를 직접 묻고, 배치·완전자동 모드는 건너뛰고 요약에만
남깁니다 — [일반 능력 A–F](#일반-능력-af-rag-집필-보조-확장) 참고). RAG로
생성한 챕터도 (a)처럼 `book-forge edit`으로 나중에 손볼 수 있습니다 — 세 경로는
배타적이지 않습니다.

**6~7. 산출물 + 품질 확인**
```bash
book-forge build html <slug>
book-forge build pdf <slug>
book-forge build slides <slug>
book-forge gate <slug> --min-gate-score 0.6   # 기준 미달 시 exit code 1 (CI 게이팅에 활용)
```

**8. 반복 — 기획/목차를 바꿔야 할 때**
```bash
book-forge plan <slug> --revise
# 기획안·목차를 다시 보여주고 승인 루프 재진입 — 목차가 바뀌면 기존에 쓴
# 챕터 본문은 chapter_no 기준으로 보존/이동하고, 삭제된 챕터는 자동 삭제하지
# 않고 목록만 보고합니다.
```

## 기능

- **기획/목차 대화형 루프**: 주제 입력 → `PlannerAgent`가 기획안 초안 → 저자가 Enter(승인)
  또는 수정 요청 입력 → 승인될 때까지 반복 → `TOCDesignerAgent`가 목차 설계 → 같은 승인
  루프 → 승인된 목차로 `Part_X/Chapter_XX.md` 스캐폴드 자동 생성
- **HTML 빌드**: 단일 자기완결 HTML — 이미지 base64 인라인 임베드(파일 첨부 없이도 열림),
  Mermaid/코드하이라이팅(CDN), `01_목차.md`에서 사이드바 자동 생성
- **PDF 빌드**: Playwright로 챕터별 A4 PDF, 이미지 자동 리사이즈
- **발표자료**: 챕터를 섹션 단위로 LLM이 압축(제목 35자 이내) — Reveal.js, 발표자 노트
  기본 포함
- **웹 에디터**: Part/Chapter 트리 + EasyMDE 마크다운 편집 + 이미지 갤러리(클릭 삽입) +
  실시간 미리보기(HTML 빌드와 동일 렌더 엔진)
- **품질 게이팅**: `book-forge gate` — agent-evaluator의 `agent-eval gate` CLI를 그대로
  위임 호출(새 판정 로직 없음), Gate A-G 가중 합성 점수·baseline 회귀·JUnit XML CI 연동
- **팀 동시성**: 웹 에디터 저장이 `LiveGuardrail(team_concurrency=...)`을 거침 — 공동
  저자가 `agent-eval claims add <Part 절대경로> --developer <이름>`으로 스코프를
  선점해두면 겹치는 저장 시도가 409로 차단됨
- **Book/AOO 마이그레이션**: 기존 Agent-Evaluator Media/Book·Media/AOO 소스를 자동 이관
- **RAG 집필 보조(옵션)**: `book-forge draft` — PDF/코드 저장소/텍스트/http(s):// URL
  소스를 Ollama 임베딩으로 청크·검색해 근거 발췌문만으로 챕터 초안 또는 레퍼런스 표
  생성. 생성 전 커버리지 점검·낮으면 대안 제안, 생성 직후 Gate 점수 즉시 노출까지
  포함(아래 일반 능력 A–F 참고)
- **지식창고 Q&A(옵션)**: `book-forge chat` — draft가 쌓은 프로젝트 지식창고에 대화형 질의

## 일반 능력 A–F (RAG 집필 보조 확장)

"AI Agent/Harness Engineering 강의를 Book-forge로 만들려면 무엇이 더 필요한가"를
분석하며 도출한 능력들 — 특정 주제 전용이 아니라 **실증 가능한 기술 콘텐츠를 요구하는
모든 강의**에 적용되는 일반 아키텍처로 설계했습니다(쿠버네티스 운영 강의 등으로 교차
검증).

| 능력 | 내용 | 구현 위치 |
|---|---|---|
| **A. 소스 어댑터 다변화** | `--source`가 PDF뿐 아니라 코드 저장소 디렉토리·마크다운/텍스트 파일·http(s):// URL을 형식/확장자/디렉토리 여부로 자동 판별 | `knowledge/sources.py` |
| **B. 콘텐츠 유형 분기** | 목차 매니페스트에 5번째 필드로 `content_type`(narrative/reference_table/diagram/exercise) 태깅 — `reference_table`이면 서술형이 아니라 표 형태로 생성 | `models.py`(`ChapterSpec.content_type`), `agents/reference_table.py` |
| **C. 근거 검증 계층** | 생성 전: 소스 코사인 유사도 평균을 점검해 낮으면 경고. 생성 후: Gate 점수를 `eval_results/`를 따로 열지 않아도 CLI에 즉시 표시 | `knowledge/store.py`(`query_with_scores`), `eval/gate_summary.py` |
| **D. 실증 가능성 게이트** | 생성 전: `exercise`/`diagram` 유형은 C의 커버리지 임계값을 더 엄격하게 적용(C의 재사용). 생성 후: `exercise`는 코드 블록 문법(`ast.parse`), `diagram`은 mermaid 구조, `reference_table`은 표 값-소스 대조를 정적으로 검증해 CLI/배치 요약에 즉시 노출(LLM 실행 없이 안전하게, 참고용) | `draft_cmd.py`의 `_STRICT_CONTENT_TYPES`, `agents/demonstration_verifier.py` |
| **E. 독자 상호작용** | 지식창고를 프로젝트에 영속화(`knowledge/store.json`)해 `book-forge draft` 세션이 끝난 뒤에도 `book-forge chat`으로 이어서 질의 | `knowledge/store.py`(`save`/`load`/`merge`), `agents/chat_agent.py` |
| **F. 대안 제안** | C에서 커버리지가 낮으면 자동 차단이 아니라 `AlternativeSuggesterAgent`가 대안 2~3개를 제시하고 저자가 진행/취소를 선택(기존 승인 루프 UX 재사용) | `agents/alternative_suggester.py` |

**배치 모드**: `book-forge draft <slug> --all --source ...`로 목차의 미집필 챕터 전부를
소스 하나로 일괄 생성합니다. 단일 모드와 저커버리지 처리 정책이 다릅니다 — 단일 모드는
F(대안 제안 + 진행/취소 확인)를 쓰지만, 배치 모드는 사람이 결과를 나중에 확인한다고
가정해 낮은 커버리지 챕터를 **LLM 호출 없이 건너뛰고** 종료 시 챕터별 Gate C 점수
요약으로 보고합니다(각 챕터는 `eval_results/draft_ch{NN}.json`으로 개별 저장 — 배치
안에서도 챕터별 점수가 뭉개지지 않습니다).

**완전 자동화**: `book-forge new "<제목>" --source ...`처럼 `new`에 `--source`를 주면
기획/목차 승인 직후 스캐폴딩에 이어 곧바로 배치 모드로 전체 챕터 초안까지 이어갑니다 —
새 로직이 아니라 `draft --all`과 동일한 함수(`collect_sources_into_store()`/
`run_batch_draft()`)를 그대로 재사용합니다. 실측: 실제 Ollama로 "주제 입력 → 승인 →
4챕터 완성"을 한 명령·76초로 완주했습니다.

## CLI 명령

| 명령 | 상태 | 설명 |
|---|---|---|
| `book-forge init` | ✅ | LLM Provider(Ollama/OpenAI/Anthropic) 및 API 키 설정 |
| `book-forge new <title> [--source ...] [--top-k] [--min-coverage]` | ✅ | 기획→목차 대화형 루프 + 스캐폴드 생성 (`--source` 주면 전체 챕터 자동 배치 초안까지) |
| `book-forge build html <slug>` | ✅ | 단일 HTML |
| `book-forge build pdf <slug> [--chapter N]` | ✅ | 챕터별 PDF |
| `book-forge build slides <slug> [--chapter N] [--without-notes]` | ✅ | Reveal.js 발표자료 |
| `book-forge edit <slug> [--port] [--no-browser]` | ✅ | 웹 에디터 |
| `book-forge gate <slug> [--min-gate-score] [--gate-thresholds] [--golden-set] [--save-baseline] ...` | ✅ | Gate A-G 판정 (agent-eval gate 전체 플래그 통과) |
| `book-forge draft <slug> <ch_no>\|--all --source ... [--top-k] [--min-coverage] [--yes] [--force]` | ✅ (선택, `[rag]`) | RAG 보조 챕터 초안/레퍼런스 표 생성 (`--all`로 일괄) |
| `book-forge chat <slug> [--top-k N]` | ✅ (선택, `[rag]`) | 프로젝트 지식창고에 대화형 질의 |
| `book-forge home [slug]` | ✅ | 데이터/프로젝트 폴더 파일 탐색기로 열기 |
| `book-forge plan <slug> [--revise]` | ✅ | 기획/목차 재검토 — `--revise` 없으면 미리보기만 |
| `book-forge scaffold <slug>` | 🚧 | (현재 `new`/`plan --revise`에 통합됨 — 독립 실행 미구현) |

미구현 명령은 `book-forge --help`에서도 확인할 수 있습니다.

## 아키텍처

```
src/book_forge/
├── agents/         # LLM 호출 에이전트 — 전부 @agent_eval 데코레이터 직접 적용
│   ├── planner.py         # PlannerAgent — propose_plan()
│   ├── toc_designer.py    # TOCDesignerAgent — design_toc()
│   ├── review_loop.py     # AuthorReviewLoop — 라운드별 개별 @agent_eval (conversation_eval 아님)
│   ├── scaffold.py        # ScaffoldAgent — @tool_guard (파일 쓰기, 사후채점 아닌 실행전 차단)
│   ├── slide_condenser.py # SlideCondenserAgent — 섹션 → TITLE/BULLET*/NOTES
│   ├── chapter_drafter.py # ChapterDrafterAgent — RAG 소스 → 챕터 초안 (rag_mode=True, 옵션)
│   ├── reference_table.py # ReferenceTableAgent — RAG 소스 → 레퍼런스 표 (B)
│   ├── alternative_suggester.py # AlternativeSuggesterAgent — 낮은 커버리지 → 대안 제안 (F)
│   ├── demonstration_verifier.py # 생성 후 정적 검증 — exercise 문법/diagram 구조/
│   │                       # reference_table 소스 대조 (D, LLM 미호출 순수 함수)
│   └── chat_agent.py      # ChatAgent — 지식창고 기반 Q&A (E)
├── knowledge/      # RAG — 소스 어댑터 + Ollama 임베딩 인메모리 코사인 유사도 검색 ([rag] extra)
│   ├── embeddings.py      # Ollama /api/embeddings, 컨텍스트 길이 초과 시 자동 축소 재시도
│   ├── store.py           # KnowledgeStore — numpy 코사인 유사도 + save/load/merge (E)
│   ├── sources.py         # 소스 어댑터 — PDF/코드 저장소/텍스트/URL 자동 판별 (A)
│   └── pdf_source.py      # PDF → 텍스트 청크 (pypdf), chunk_text() 공용 청커
├── publish/        # 마크다운 → HTML/PDF/Slides (Book/AOO 엔진 이식)
│   ├── markdown_engine.py # @@HTML_START@@, Mermaid, base64 이미지 임베딩
│   ├── html_builder.py / pdf_builder.py / slide_builder.py
│   └── toc_loader.py      # 01_목차.md → 실제 파일 경로
├── editor/         # Flask 웹 에디터 (Part/Chapter 트리 + 이미지 갤러리)
├── eval/           # PerformanceMonitor 팩토리 + gate_summary.py(Gate 점수 즉시 조회, C)
├── llm/            # create_llm() — Ollama/OpenAI/Anthropic 통합 인터페이스
├── models.py       # ChapterSpec, parse_toc_manifest (```toc 매니페스트)
└── cli/            # Click 진입점
```

**사용자 데이터**: `~/Documents/BookForge/projects/<slug>/`
```
<slug>/
├── 00_기획안.md   01_목차.md
├── Part_X_.../Chapter_XX_....md (+ images/)
├── outputs/ (html · pdf/ · *_slides.html)
├── knowledge/store.json (RAG 지식창고 — draft가 쌓고 chat이 재사용, [rag] extra)
└── eval_results/ (*.json, *.html — agent-evaluator 계측 결과)
```

## Gate A–G 계측

모든 LLM 호출 에이전트가 `@agent_eval`을 직접 사용합니다(Lecture_forge가 Pydantic 반환값
때문에 Adapter 클래스를 따로 둔 것과 달리, Book-forge 에이전트는 산출물이 처음부터
마크다운 문자열이라 `(str, EvalMetadata)` 반환 계약과 자연히 맞습니다).

| 에이전트 | 데코레이터 | 핵심 Config |
|---|---|---|
| PlannerAgent | `@agent_eval` | `GoalAlignmentConfig`, `InstructionConfig`, `ExplainabilityConfig` |
| TOCDesignerAgent | `@agent_eval` | `PlanConfig`, `SubtaskConfig`, `ContextRetentionConfig` |
| AuthorReviewLoop | `@agent_eval`(라운드별) | `LoopDetectionConfig` — **`conversation_eval`은 쓰지 않음**(아래 참고) |
| ScaffoldAgent | `@tool_guard` | `LoopDetectionConfig`(LiveGuardrail) — 경로 포함 검사는 직접 구현 |
| SlideCondenserAgent | `@agent_eval` | `InstructionConfig`, `ExplainabilityConfig`, `SLAConfig` |
| ChapterDrafterAgent | `@agent_eval(rag_mode=True)` | `HallucinationDetector`(자동 활성화), `SLAConfig`, `ThreatSeverityConfig` |
| ReferenceTableAgent | `@agent_eval(rag_mode=True)` | ChapterDrafterAgent와 동일 배선, 산출물만 표 형태 |
| AlternativeSuggesterAgent | `@agent_eval` | `InstructionConfig`, `ExplainabilityConfig` |
| ChatAgent | `@agent_eval(rag_mode=True)` | `HallucinationDetector`(자동 활성화), `SLAConfig` |

> **왜 `conversation_eval`이 아닌가**: 실제 소스(`decorators.py`의
> `_CONVERSATION_EVAL_UNUSED_HARNESS_PARAMS`)를 확인한 결과, `conversation_eval`은
> 30개 Harness Config 전부를 시그니처로만 받고 평가에 반영하지 않습니다(SPEC-039
> REQ-5, Non-Goal). 저자 리뷰 루프에서 `LoopDetectionConfig`가 실제로 작동해야 하므로,
> 각 라운드를 독립된 TaskResult로 기록하는 `@agent_eval` 개별 호출 방식을 씁니다.

`book-forge gate <slug>`는 최신 `eval_results/*.json`을 대상으로 agent-evaluator의
`agent-eval gate` CLI를 그대로 위임 호출합니다(새 판정 로직 없음).

## Book/AOO 마이그레이션

Agent-Evaluator 레포의 `Media/Book`, `Media/AOO`처럼 `ORDERED_FILES` 하드코딩 + `MERMAID_INJECTIONS` 딕셔너리 방식으로 관리되던 기존 도서를 이관합니다.

```bash
python scripts/migrate_legacy_book.py \
  --source /path/to/Agent-Evaluator/Media/Book \
  --build-module build_book \
  --target-slug agent-evaluator-harness-book
```

- `ORDERED_FILES` → `01_목차.md` 선언적 매니페스트로 변환(책 전체 기준 챕터 번호 재부여)
- 각 챕터의 `images/` 디렉토리를 새 위치로 복사(상대경로 참조라 내용 수정 불필요)
- `MERMAID_INJECTIONS`는 앵커 텍스트가 일치하는 경우에만 자동 인라인화 — 일치하지
  않는 항목은 **자동 반영하지 않고** 콘솔에 목록으로 보고합니다(수동 확인 유도)

## 알려진 한계

- **`plan --revise`의 챕터 매칭은 chapter_no 기준**: 안정된 챕터 ID가 없어 "저자가
  기존 챕터 순서를 재배열하지 않고 앞/뒤로 추가·삭제만 한다"고 가정합니다. 같은
  chapter_no에서 제목만 바뀌면 기존 본문을 새 경로로 이동해 보존하고, 목차에서
  완전히 빠진 chapter_no는 파일을 **삭제하지 않고** 남겨둔 채 콘솔에 목록만
  보고합니다(정리는 저자가 수동으로).
- **PDF의 Mermaid 렌더링**: Book/AOO 원본의 정교한 SVG 청크 캡처를 이식하지 않고
  `startOnLoad` 대기 후 인쇄하는 단순화된 경로를 씁니다 — 매우 큰 다이어그램은
  페이지 경계에서 잘릴 수 있습니다.
- **HTML/PDF/Slides 빌드는 CDN 의존**: Mermaid.js/highlight.js/Reveal.js를 CDN에서
  불러옵니다. LLM 호출(기획/목차/집필/슬라이드 압축)은 Ollama로 완전 오프라인이 가능하지만,
  **PDF 빌드는 Playwright가 그 CDN 스크립트를 실제로 로드해야 하므로 빌드 시점에 네트워크가
  필요**합니다. HTML/발표자료 결과물도 "브라우저로 열어볼 때" 네트워크가 필요합니다(생성
  자체는 오프라인 가능).
- **팀 동시성은 opt-in 워크플로**: `TeamConcurrencyConfig`는 스코프를 실제로
  "claim"해둔 경우에만 충돌을 감지합니다 — `agent-eval claims add`를 아무도 안 쓰면
  검사가 항상 통과합니다(새 클레임 관리 로직을 만들지 않고 SDK 관례를 그대로 재사용).
- **RAG 임베딩은 Ollama 전용**: chat LLM provider가 OpenAI/Anthropic이어도 `book-forge
  draft`의 임베딩은 항상 로컬 Ollama(`OLLAMA_EMBED_MODEL`, 기본 `mxbai-embed-large`)를
  씁니다 — 별도 provider별 임베딩 API 통합은 하지 않았습니다.
- **RAG 초안의 출력 형식 안정성**: 로컬 모델이 가끔 전체 응답을 ` ```markdown ` 코드
  펜스로 감싸는 등 프롬프트 지시를 완벽히 지키지 않을 수 있습니다 — 초안은 항상
  사람이 검토·정리한다는 전제입니다. `HallucinationDetector`가 근거 없는 서술을
  Gate C 점수(warn/fail)로 잡아내므로, 초안 승인 전 `book-forge gate`로 확인을
  권장합니다.
- **RAG 소스 누출(실측 확인)**: `--source`로 넣은 코드 저장소에 프롬프트 템플릿·예시
  텍스트가 포함돼 있으면(예: Book-forge 자신의 `agents/prompts.py`), 검색된 청크에
  그 형식(`ALT:`, `TITLE:/BULLET:/NOTES:`, ` ```toc ` 블록 등)이 섞여 있을 때 LLM이
  본문 내용 대신 그 형식을 그대로 흉내 내거나 문미에 이어 붙이는 현상을 실제로
  확인했습니다. 소스로 코드 저장소를 쓸 때는 결과물을 반드시 검토하세요.
- **커버리지 사전 점검은 전체 지식창고 기준**: E(영속 지식창고)와 C(사전 점검)가
  결합되면서, `--min-coverage` 점검이 이번에 새로 추가한 `--source`만이 아니라
  프로젝트에 누적된 지식창고 전체를 대상으로 검색합니다 — 새 소스 자체는 무관해도
  기존에 쌓인 소스가 그럴듯하게 걸리면 낮은 커버리지 경고가 안 뜰 수 있습니다(실측
  확인: 무관한 텍스트를 추가했는데도 기존 코드 소스 때문에 평균 유사도 0.77로
  임계값을 통과함).
- **임베딩 컨텍스트 길이**: `mxbai-embed-large`는 청크가 너무 길면(코드 저장소 청크
  1200자에서 실제로 500 에러 재현) 실패합니다 — 코드 소스 청크 기본값을 500자로
  낮추고, 그래도 초과하면 절반으로 잘라 1회 자동 재시도합니다(`knowledge/embeddings.py`).
- **URL 소스는 정적 HTML만 지원**: `--source https://...`는 표준 라이브러리
  `html.parser`로 `<script>/<style>/<head>`만 제거하고 나머지 텍스트를 그대로
  모읍니다(trafilatura/readability 같은 본문 추출 전용 라이브러리 미사용 — 의존성
  최소화 원칙). 네비게이션·푸터 등 잡음이 섞여 나올 수 있고, JS로 본문을 렌더링하는
  SPA 페이지는 텍스트를 거의 못 가져옵니다. 재귀적으로 링크를 따라가지 않고 지정한
  URL 1개만 가져오며, 리다이렉트/robots.txt는 별도로 존중하지 않으므로 저자 본인이
  권한이 있거나 공개된 자료만 지정하세요.

## 개발

```bash
pip install -e ".[dev,pdf,serve,rag]"
playwright install chromium
pytest                 # 140개 테스트
ruff check src tests scripts
python -m build --wheel   # 패키징 검증 (editor/templates/*.html 포함 여부 확인 필수)
```

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
