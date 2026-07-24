# Book-forge

AI 협업 다권 도서 저술 파이프라인 — 주제 → 기획안/목차(저자 상호작용) → 마크다운 집필 →
HTML/PDF/발표자료. 전 과정을 [agent-evaluator](https://pypi.org/project/agent-evaluator/)
Gate A–G로 계측·게이팅합니다. LLM Provider는 기본값이 **Ollama(로컬)** — API 키 없이
바로 시작할 수 있습니다.

**핵심 통계**: 14개 에이전트(`@agent_eval`/`@tool_guard` 데코레이터 직접 적용) | CLI 명령
15개(14개 동작) | 408개 테스트 | Python 3.11+

## 목차

- [설치](#설치)
- [사용자 작업 흐름](#사용자-작업-흐름)
- [기능](#기능)
- [일반 능력 A–F (RAG 집필 보조 확장)](#일반-능력-af-rag-집필-보조-확장)
- [일반 능력 G — 자기실증 예제 (멀티에이전트 협업)](#일반-능력-g--자기실증-예제-멀티에이전트-협업)
- [일반 능력 H — 구조적 코드 인덱싱](#일반-능력-h--구조적-코드-인덱싱)
- [일반 능력 I — 로컬 코드베이스 대상 검증](#일반-능력-i--로컬-코드베이스-대상-검증)
- [일반 능력 J — 지식창고 라이프사이클 관리](#일반-능력-j--지식창고-라이프사이클-관리)
- [일반 능력 O — 목차 개정 이력 자동 기록](#일반-능력-o--목차-개정-이력-자동-기록)
- [일반 능력 M — 챕터 구조 템플릿](#일반-능력-m--챕터-구조-템플릿)
- [일반 능력 K — 소스 가중치 균형 조정](#일반-능력-k--소스-가중치-균형-조정)
- [일반 능력 N — 리서치 에이전트 + 참고 자료 자동 인용](#일반-능력-n--리서치-에이전트--참고-자료-자동-인용)
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

Gate 판정 가중치(`gate_a_tcr_weight`/`gate_c_tcr_weight`/`gate_b_loop_weight`,
agent-evaluator 기본값 사용)를 프로젝트마다 다르게 쓰려면 `.env`에
`BOOK_FORGE_GATE_A_TCR_WEIGHT`/`BOOK_FORGE_GATE_C_TCR_WEIGHT`/
`BOOK_FORGE_GATE_B_LOOP_WEIGHT`를 설정하세요(미지정 시 기존 기본값 그대로).

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
  루프 → 승인된 목차로 `Part_X/Chapter_XX.md` 스캐폴드 자동 생성. `book-forge new --source
  <코드 저장소>`를 주면 목차 설계 **이전에** H로 실제 모듈/클래스 목록을 미리 분석해
  반영한다(일반 능력 S) — 존재하지 않는 서브시스템을 챕터로 지어내는 걸 방지
- **HTML 빌드**: 단일 자기완결 HTML — 이미지 base64 인라인 임베드(파일 첨부 없이도 열림),
  Mermaid/코드하이라이팅(CDN), `01_목차.md`에서 사이드바 자동 생성. `--author` 등을
  지정했으면 표지 페이지(제목/저자/판/저작권 고지) 자동 삽입(일반 능력 AI)
- **PDF 빌드**: Playwright로 챕터별 A4 PDF, 이미지 자동 리사이즈. 표지 정보가 있으면
  `00_표지.pdf`를 별도 파일로 함께 생성
- **발표자료**: 챕터를 섹션 단위로 LLM이 압축(제목 35자 이내) — Reveal.js, 발표자 노트
  기본 포함. 코드/mermaid 펜스는 LLM 요약 이전에 분리해 원문 그대로 별도
  슬라이드로 보존(Mermaid.js/highlight.js CDN 로드 포함, 일반 능력 P/Q)
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
- **지식창고 Q&A(옵션)**: `book-forge chat` — draft가 쌓은 프로젝트 지식창고에 대화형 질의.
  세션 전체를 `ConversationSession`으로 감싸 최근 대화를 프롬프트에 포함(이어지는 질문
  이해)하고, 종료 시 맥락 유지/주제 일관성 등 4개 지표를 표시
- **다관점 리뷰 패널**: `book-forge review` — 정확성/가독성 검토자 2명이 챕터를 독립
  검토하고 편집장(ChiefEditorAgent)이 종합 판정. Book-forge 최초의 진짜 감독자-작업자
  멀티에이전트 협업 예제(아래 일반 능력 G 참고)
- **코드-본문 정합성 검사(옵션)**: `book-forge draft ... --check-package agent_evaluator` —
  본문이 언급한 `import`/백틱 심볼이 실제로 그 패키지에 존재하는지 정적으로 대조(LLM
  미호출, C의 확장). 프로젝트가 처음 사용한 시점의 SDK 버전을 `sdk_versions.json`에
  고정하고, 이후 설치 버전이 달라지면 경고
- **코드 예제 실행 검증(옵션)**: `--check-package`와 함께 `--execute-examples`를 주면
  python 코드 블록을 별도 subprocess에서 실제로 실행해 성공하는지 확인(타임아웃 10초,
  LLM이 생성한 코드를 실행하는 위험을 인지하고 명시적으로 켜야 하는 옵트인)
- **실습/캡스톤 스캐폴드**: `content_type: capstone`으로 태깅한 챕터는 빈 템플릿(TODO
  있는 스켈레톤)과 별도 정답 파일을 함께 생성 — 독자가 직접 풀어보는 실습 전용
  (아래 일반 능력 B 표 참고)

## 일반 능력 A–F (RAG 집필 보조 확장)

"AI Agent/Harness Engineering 강의를 Book-forge로 만들려면 무엇이 더 필요한가"를
분석하며 도출한 능력들 — 특정 주제 전용이 아니라 **실증 가능한 기술 콘텐츠를 요구하는
모든 강의**에 적용되는 일반 아키텍처로 설계했습니다(쿠버네티스 운영 강의 등으로 교차
검증).

| 능력 | 내용 | 구현 위치 |
|---|---|---|
| **A. 소스 어댑터 다변화** | `--source`가 PDF뿐 아니라 코드 저장소 디렉토리·마크다운/텍스트 파일·http(s):// URL을 형식/확장자/디렉토리 여부로 자동 판별. 코드 저장소는 텍스트 청크에 더해 정적 분석 구조 요약도 자동 포함(H) | `knowledge/sources.py`, `knowledge/code_index.py` |
| **B. 콘텐츠 유형 분기** | 목차 매니페스트에 5번째 필드로 `content_type`(narrative/reference_table/diagram/exercise/capstone/module_reference) 태깅 — `reference_table`은 표, `diagram`은 Mermaid 다이어그램, `capstone`은 **빈 템플릿+별도 정답 파일 2개**, `module_reference`(T)는 RAG 대신 H의 구조 인덱스를 그대로 순회해 **전체 커버리지가 보장되는** 표로 전용 생성기 분기(narrative/exercise는 ChapterDrafterAgent가 한 파일에 담당) | `models.py`(`ChapterSpec.content_type`), `agents/reference_table.py`, `agents/diagram_generator.py`, `agents/capstone_generator.py`, `agents/module_reference.py` |
| **C. 근거 검증 계층** | 생성 전: 소스 코사인 유사도 평균을 점검해 낮으면 경고. 생성 후: Gate 점수를 `eval_results/`를 따로 열지 않아도 CLI에 즉시 표시. `--check-package`를 주면 본문이 언급한 import/백틱 심볼이 실제 패키지(설치된 패키지 또는 로컬 디렉토리, I)에 존재하는지도 정적으로 대조(옵트인) — 이 검사의 기준 버전을 프로젝트별로 `sdk_versions.json`에 고정(패키지는 pip 버전, 로컬은 git 커밋)하고 드리프트를 경고. `--execute-examples`를 함께 주면 python 코드 블록을 subprocess로 실제 실행해 검증(로컬 대상은 PYTHONPATH 자동 주입, 타임아웃, 별도 옵트인) | `knowledge/store.py`(`query_with_scores`), `eval/gate_summary.py`, `agents/code_consistency_checker.py`, `agents/sdk_version_pin.py`, `agents/code_example_verifier.py` |
| **D. 실증 가능성 게이트** | 생성 전: `exercise`/`diagram`/`capstone`/`module_reference` 유형은 C의 커버리지 임계값을 더 엄격하게 적용(C의 재사용). 생성 후: `exercise`는 코드 블록 문법(`ast.parse`), `diagram`은 mermaid 구조 + (옵트인) 노드 라벨이 소스에 등장하는지 그라운딩 대조(U), `reference_table`은 표 값-소스 대조, `capstone`은 템플릿의 TODO 존재+정답의 완성도(TODO 없음), `module_reference`는 H가 나열한 항목이 전부 본문에 등장하는지(T)를 정적으로 검증해 CLI/배치 요약에 즉시 노출(LLM 실행 없이 안전하게, 참고용) | `draft_cmd.py`의 `_STRICT_CONTENT_TYPES`, `agents/demonstration_verifier.py` |
| **E. 독자 상호작용** | 지식창고를 프로젝트에 영속화(`knowledge/store.json`)해 `book-forge draft` 세션이 끝난 뒤에도 `book-forge chat`으로 이어서 질의. 세션은 `ConversationSession`으로 감싸 최근 3턴을 프롬프트에 포함하고(이어지는 질문 이해), 종료 시 context_retention 등 4개 지표를 표시 | `knowledge/store.py`(`save`/`load`/`merge`), `agents/chat_agent.py`, `cli/commands/chat_cmd.py` |
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

**코드-본문 정합성 검사(C의 확장)**: `--check-package <패키지명>`을 주면 본문이 언급한
`from X import Y`/`import X`와 백틱으로 감싼 `PascalCase` 심볼(`` `ScopeConfig` ``,
`` `ScopeConfig.allowed_tools` `` 등)을 실제로 그 패키지에서 `importlib`로 대조합니다.
`ast.parse()`가 코드 블록의 **문법**만 보는 것과 달리, 이건 "그 이름이 실제로
존재하는가"를 봅니다 — `from agent_evaluator import ScopeConfig`는 문법적으로 완벽해도
`ScopeConfig`가 실제로 그 이름으로 있는지, `ScopeConfig.path`처럼 존재하지 않는 필드를
언급했는지는 별개 문제입니다. `dataclasses.field(default_factory=...)` 필드는
`hasattr()`만으로는 놓치므로(실측 확인) `dataclasses.fields()`도 함께 봅니다. `None`/
`ValueError` 같은 Python 표준 어휘는 대상 패키지 소속이라 주장한 적이 없으므로
검사에서 제외합니다. LLM을 호출하지 않는 순수 정적 분석이며, 실패해도 초안 저장을
막지 않습니다(참고용).

**SDK 버전 고정 메타데이터(C 확장의 기준)**: `--check-package`는 지금까지 "그 순간
설치된" 버전을 암묵적으로 기준 삼았습니다 — 오늘 0.9.9로 챕터를 쓰고 몇 달 뒤 환경이
1.2.0으로 올라간 채로 같은 프로젝트에 다시 검사를 돌리면, "본문이 틀렸다"와 "SDK가
바뀌었다"를 구분할 방법이 없었습니다. 프로젝트가 `--check-package`를 처음 쓴 시점의
설치 버전을 `sdk_versions.json`에 한 번 고정해두고(이후 자동으로 덮어쓰지 않음),
이후 호출마다 현재 설치 버전과 대조합니다 — 달라졌으면 "코드-본문 정합성 검사가 다른
버전을 기준으로 판정될 수 있다"는 경고를 CLI에 표시하고, 검사 결과 옆에 어느 버전
기준인지(`(agent_evaluator 0.9.9 기준)`)를 항상 표시합니다. Book/AOO의
`build_book.py`가 `pyproject.toml`에서 버전을 자동으로 읽어 표지에 찍던 관례를
재해석한 것입니다 — Book-forge 자신이 아니라 저자가 근거로 삼는 **대상 SDK**의
버전을 고정한다는 점이 다릅니다.

**코드 예제 실행 검증(C의 세 번째 검증기 종류)**: `demonstration_verifier.verify_exercise_code()`는
`ast.parse()`로 **문법**만 봅니다 — 실제로 실행하면 성공하는지는 지금까지 한 번도
확인하지 않았습니다. 이 프로젝트는 그 결정을 CLAUDE.md에 명시적으로 기록해뒀습니다
("LLM이 생성한 임의 코드를 자동으로 실행하지는 않는다"). `--check-package`와 함께
`--execute-examples`를 켜면 그 결정을 뒤집는 게 아니라 **별도의 명시적 옵트인
계층**으로 실행 검증을 추가합니다:
- 코드 블록마다 별도 `subprocess`(타임아웃 10초)로 격리 실행합니다 — in-process
  `exec()`가 아니므로 크래시가 CLI 자체를 죽이지 않고, 부모 프로세스의 메모리(API
  키가 담긴 환경 변수 등)에 직접 접근하지 못합니다. 단, 파일시스템/네트워크 접근은
  OS 수준으로 격리되지 않습니다(컨테이너 없는 순수 Python subprocess의 한계 — 알려진
  한계 참고).
- `narrative`/`exercise`는 생성된 코드 전체를, `capstone`은 **정답(solution)만**
  실행합니다 — 템플릿은 `TODO`/`NotImplementedError`로 의도적으로 미완성이라
  실행하면 항상 "실패"로 나와 무의미하기 때문입니다.
- 다른 검증과 같은 원칙으로 **실패해도 초안 저장을 막지 않습니다**(참고용) —
  원 설계 문서는 "실패 시 초안 반려"를 제안했지만, exercise/diagram/capstone/
  code_consistency 전부가 지켜온 "경고만 하고 저장은 유지" 원칙을 깨지 않는 쪽을
  택했습니다.
- 실측(실제 Ollama): 정상 실습 코드(`reversed()`/슬라이싱으로 리스트 뒤집기)가
  실제로 실행에 성공함을 확인했고, 오프라인 결정론적 테스트로 문법 오류/런타임
  예외(assert 실패, ImportError)/타임아웃 3가지 실패 경로를 모두 검증했습니다.

**실습/캡스톤 스캐폴드(B의 네 번째 콘텐츠 유형)**: `content_type`을 `capstone`으로
태깅하면(목차의 5번째 필드) 기존 `exercise`("목표→코드→해설"을 한 파일에 담음)와
다른 패턴으로 생성됩니다 — 독자가 실제로 풀어볼 **빈 템플릿**(TODO가 있는 미완성
스켈레톤)을 챕터 파일에, **모범 정답+해설**을 별도 사이드카 파일(`Chapter_XX_제목_정답.md`)에
나눠 씁니다. 템플릿과 정답은 한 번의 LLM 호출·같은 컨텍스트에서 `=== TEMPLATE ===`/
`=== SOLUTION ===` 구분자로 함께 생성됩니다(두 번 호출하면 서로 다른 문제를 다룰
위험이 있음). `book-forge build`/`edit`는 `01_목차.md` 매니페스트만 읽으므로
(`load_toc()`, 디렉토리 스캔이 아님) 정답 사이드카 파일은 HTML/PDF/발표자료/웹 에디터
어디에도 노출되지 않습니다 — 실측(실제 Ollama)으로 빌드된 HTML에 정답 코드가 전혀
섞이지 않음을 확인했습니다.

**지속형 상호작용 강화(E)**: 처음 구현한 `book-forge chat`은 매 질문이 완전히
독립적이었습니다 — "방금 말한 그 메서드는 원본을 바꾸나요?" 같은 이어지는 질문을 이해할
수 없었습니다. `chat_cmd.py`가 세션 전체를 agent-evaluator의 `ConversationSession`
(`monitor.conversation(...)`)으로 감싸도록 확장했습니다:
- 최근 3턴을 `--- 이전 대화 ---` 섹션으로 프롬프트에 포함(`agents/chat_agent.py`의
  `conversation_history` 파라미터) — RAG 근거(`sources`)와는 별개 채널이라
  `HallucinationDetector`의 환각 채점 기준(지식창고 발췌문)에는 영향을 주지 않습니다.
- 세션 종료(`/exit` 또는 Ctrl-D) 시 `context_retention`/`topic_coherence`/
  `progressive_depth`/`session_completion` 4개 지표를 자동 계산해 CLI에 표시하고
  `eval_results/chat.json`의 `conversation_sessions`에 턴별 기록과 함께 저장합니다.
  Gate A-G 점수에는 반영되지 않는 순수 운영 지표입니다(`ConversationSession`은
  25개 Native Tracker 중 "operational support" 8종에 속함).
- 실측(실제 Ollama): "reverse() 메서드는 어떻게 동작해?" → "**방금 말한 그** 메서드는
  원본을 바꾸는 거야 새로 만드는 거야?"를 연달아 질문했을 때, 두 번째 답변이 지시어
  "그 메서드"를 `reverse()`로 정확히 이해해 답했습니다(대화 이력 없이는 불가능).

## 일반 능력 G — 자기실증 예제 (멀티에이전트 협업)

A–F는 RAG 집필 보조 확장이지만, G는 다른 축입니다: **강의가 가르치는 개념(예:
멀티에이전트 협업·오케스트레이션)을 저작 도구 자신이 최소 1회는 실제로 실행해봐야
한다**는 요구에서 나왔습니다. Book-forge의 기존 6개 에이전트(Planner→TOCDesigner→
ReviewLoop→Scaffold→ChapterDrafter→SlideCondenser)는 전부 순차 파이프라인이라, 아무리
`book-forge gate`를 돌려도 Gate F(Multi-Agent Coordination)는 항상 N/A였습니다.

`book-forge review <slug> <chapter_no>`가 처음으로 진짜 감독자-작업자(supervisor-worker)
패턴을 구현합니다 — 합성 데모가 아니라 "초안을 승인 전에 다관점으로 검토"하는 실사용
기능입니다:

1. **정확성 검토자**와 **가독성 검토자**(worker)가 같은 챕터를 서로 다른 관점에서
   독립적으로 검토해 `VERDICT: APPROVE`/`REVISE`를 냅니다.
2. **편집장**(ChiefEditorAgent, supervisor)이 두 판정을 종합합니다 — 판정이 갈리면
   그 불일치를 명시적으로 언급하고 조정해 최종 결론을 냅니다.

이 한 번의 실행이 Gate F의 지금까지 비어있던 4개 지표를 전부 실제 값으로 채웁니다:

| 지표 | 어떻게 채워지는가 |
|---|---|
| `coordination_score` | 편집장↔검토자 위임/응답을 `AgentCoordinationTracker.track_interaction()`으로 실제 기록 |
| `avg_consensus` | 검토자 판정(VERDICT)을 구조화 신호(`agent_interactions=[{"agent","intent"}]`)로 `eval_consensus()`에 직접 전달 — 자유 텍스트 어휘 유사도가 아니라 판정 자체의 일치 여부로 계산(SPEC-009 REQ-1) |
| `avg_role_compliance` | 각 검토자가 담당 관점(`AgentRoleConfig.allowed_action_keywords`)을 실제로 언급하고 다른 관점(`forbidden_action_keywords`)을 침범하지 않는지 |
| `avg_conflict_resolution` | 편집장 응답 텍스트를 `ConflictResolutionConfig` 기본 한국어 마커("충돌"/"불일치" vs "해결"/"합의")로 판정 |

실측(실제 Ollama): 두 검토자가 합의(승인)한 정상 챕터에서 `consensus_score=1.0`,
편집장이 승인했고 `book-forge gate`의 Gate F가 **0.953(pass)**로 처음 N/A를 벗어남을
확인했습니다. 의도적으로 사실 오류(파이썬 리스트를 C++ std::vector로 잘못 서술)를 심은
챕터에서는 두 검토자가 각자 다른 근거(정확성 검토자는 사실 오류, 가독성 검토자는 구조
문제)로 REVISE 판정을 내렸고, 편집장이 두 근거를 모두 반영해 REVISE로 최종 결론을 낸
것도 확인했습니다.

`PropagationConfig`(정보 전파 충실도)는 이번 범위에 포함하지 않았습니다 — 자유 텍스트
근거를 key_facts로 어휘 매칭하는 건 한국어 토큰 분할 특성상 오탐이 잦습니다.

## 일반 능력 H — 구조적 코드 인덱싱

"개념 설명 + 동작 설명 + **특정 프로젝트 소스코드 분석** + 활용"형 강의를 분석하며
도출한 능력입니다. A(소스 어댑터)의 코드 저장소 어댑터는 파일을 텍스트로 청크·임베딩할
뿐입니다 — "이 프로젝트에 어떤 모듈이 있는가", "A가 B를 어떻게 의존하는가" 같은
**파일 간 구조적 관계**는 청크 유사도 검색으로 잘 안 잡힙니다(import문이 청크
경계에서 잘리거나, 애초에 그래프 구조가 텍스트 나열에는 없습니다).

`knowledge/code_index.py`가 `.py` 파일을 표준 라이브러리 `ast`로 정적 분석해
모듈/클래스/함수 인벤토리 + 내부/외부 의존 관계를 뽑아내고, `load_code_repo_source()`가
이 결과를 별도 청크로 **추가**합니다(청크 검색을 대체하는 게 아니라 보강) — 기본으로
켜져 있고, `book-forge draft ... --source <코드 저장소>`를 쓰면 자동으로 포함됩니다.

- **Python만 지원**: `ast`가 표준 라이브러리라 새 의존성이 필요 없습니다(tree-sitter 등
  다국어 파서는 추가하지 않았습니다 — 의존성 최소화 원칙). `.py`가 없는 저장소는 조용히
  건너뛰고 기존 청크 검색 경로만 씁니다.
- **내부/외부 의존 구분**: import의 첫 세그먼트가 인덱싱 루트 디렉토리 자신의 이름이거나
  바로 아래 서브디렉토리 이름과 같으면 "내부 의존"으로 분류합니다 — 완벽한 import
  해석기가 아니라(상대 import·`sys.path` 조작까지는 못 따라감) "대략 구분하는 근거"가
  목적인 휴리스틱입니다.
- **문법 오류 파일은 조용히 제외**: 저장소 하나에 문법 오류 파일이 있어도 전체 인덱싱이
  중단되지 않습니다.

실측(실제 Ollama): Book-forge 자신의 `agents/` 패키지(18개 모듈)를 `--source`로 써서
"agents 패키지 구조 분석" 챕터를 생성했더니, `PlannerAgent`/`AlternativeSuggesterAgent`/
`ChiefEditorAgent` 등 실제 클래스·역할을 정확히 서술하고 `demonstration_verifier.py`/
`diagram_generator.py` 같은 실제 모듈명까지 정확히 언급하는 걸 확인했습니다 — 순수
청크 검색만으로는 이 정도의 구조적 일관성을 기대하기 어렵습니다.

## 일반 능력 I — 로컬 코드베이스 대상 검증

H와 같은 강의 유형 분석에서 나온 또 다른 공백입니다: `--check-package`/`--execute-examples`
(C의 확장)는 지금까지 `importlib.import_module()`로 **설치된 패키지**만 대상으로
삼을 수 있었습니다 — "특정 프로젝트 소스코드 분석" 강의는 분석 대상이 보통 `pip
install` 안 한, 그냥 클론해온 로컬 저장소입니다. 기존 방식으로는 이런 경우 항상
`ImportError`만 났습니다.

`--check-package`에 설치된 패키지명 대신 **로컬 디렉토리 경로**를 주면
(`Path(...).is_dir()`로 자동 감지, 새 CLI 플래그 없음) 세 검증이 전부 로컬 모드로
전환됩니다:

| 검증 | 설치된 패키지 모드 | 로컬 디렉토리 모드 |
|---|---|---|
| 코드-본문 정합성 | `importlib.import_module()`로 심볼 존재 확인 | H(구조적 코드 인덱싱)의 정적 분석 결과로 대조 — 새 파싱 로직 없이 이미 검증된 인프라 재사용 |
| SDK 버전 고정 | `importlib.metadata.version()` | git 커밋 해시(짧게)+dirty 여부(`agent-evaluator` 자신의 `agent_version="auto"`와 같은 원리). git 저장소가 아니면 버전 추적 없이 조용히 스킵 |
| 코드 실행 검증 | 이미 설치된 환경이라 그대로 실행 | 대상 디렉토리(+부모 디렉토리)를 subprocess의 `PYTHONPATH`에 추가해 로컬 import가 풀리게 함 |

- **정합성 검사는 "정확한 서브모듈"이 아니라 "프로젝트 어딘가에 존재하는가"를
  봅니다**: 로컬 디렉토리 경로를 dotted import 경로로 신뢰성 있게 매핑할 방법이
  없어서(대상이 패키지 루트인지 그 서브디렉토리인지 알 수 없음), 대상 디렉토리
  전체에서 발견한 클래스/함수 이름을 평평한 집합으로 모아 대조합니다 — import
  경로가 대상 디렉토리 소속으로 보이는지만 먼저 거르고(경로의 어느 세그먼트든
  일치하면 인정 — 첫 세그먼트만 보면 대상을 서브디렉토리로 지정했을 때 놓치는
  걸 실측으로 확인해 완화했습니다), 소속으로 보이면 평평한 심볼 집합과 대조합니다.
- **`PYTHONPATH` 경로는 절대 경로로 정규화합니다**: subprocess의 작업 디렉토리가
  임시 디렉토리라, 상대 경로를 그대로 넣으면 엉뚱한 곳을 가리킵니다(실측으로 발견한
  버그 — 상대 경로를 넣었더니 `ModuleNotFoundError`가 계속 재현됐습니다).

실측(실제 Ollama): 어디에도 설치되지 않은 독립 로컬 패키지(`toylib`)를 만들어
`--check-package /path/to/toylib --execute-examples`로 분석했더니, 생성된 실습
챕터가 `from toylib.calculator import make_calculator`를 실제로 import해 실행에
성공하는 걸 확인했습니다(PYTHONPATH 주입 없이는 애초에 import가 불가능한
패키지였습니다). git 저장소로 만든 뒤 재실행하니 `(toylib git 6eb099b 기준)`처럼
커밋 해시 기준 버전 표시도 정상 동작했습니다.

## 일반 능력 J — 지식창고 라이프사이클 관리

Media/AOO 대비 품질 분석과 별개로, 실전 6챕터 집필(`AI_에이전트_평가_입문` 프로젝트) 중
직접 겪은 문제에서 도출한 능력입니다: `KnowledgeStore.add()`는 중복 제거가 없고,
`collect_sources_into_store()`는 항상 기존 `store.json`을 불러와 append만 합니다 —
소스를 잘못 골랐을 때(실측: OpenCode 플러그인 TypeScript 파일 하나가 한 번 섞여
들어간 뒤 그 심볼들이 이후 여러 챕터의 검색 결과를 계속 오염시켰습니다) 되돌릴 방법이
"`store.json`을 직접 `rm`"밖에 없었습니다.

`book-forge knowledge status <slug>`는 청크의 `# 파일:`/`# 출처:` 태그를 파싱해
소스별 청크 분포를 보여주고, `book-forge knowledge reset <slug>`는 지식창고를
통째로 삭제합니다(확인 프롬프트 필수, `--yes`로 스킵 가능). 둘 다 새 판정 로직 없이
기존 `KnowledgeStore.load()`/파일 삭제만 감싼 얇은 CLI 래퍼입니다.

- **소스별 집계는 참고용입니다**: `chunk_text()`가 파일을 여러 청크로 쪼갤 때 태그
  줄이 모든 조각에 남는다는 보장이 없고(overlap 크기에 따라 다름), PDF 소스는 애초에
  태깅하지 않습니다 — 태그를 못 찾은 청크는 "(태그 없음)"으로 묶어 보여줍니다.
- **`reset`은 삭제만 합니다**: 소스 목록 재선정이나 재임베딩은 여전히 `book-forge
  draft ... --source ...`(빈 지식창고에서 새로 시작)가 담당합니다 — 이 명령은 "다시
  시작할 수 있게 비우는 것"까지만 책임집니다.

## 일반 능력 O — 목차 개정 이력 자동 기록

Media/AOO의 목차 파일(`02_목차_초안.md`)에는 "2026-07-14 개정 ①/②/③"처럼 무엇을·왜
바꿨는지 날짜와 함께 누적 기록하는 개정 이력이 있습니다 — Book-forge의
`book-forge plan --revise`는 지금까지 목차를 바꿀 때마다 이전 내용을 조용히
덮어썼습니다.

`plan --revise`가 저자 피드백을 실제로 반영해 목차를 개정할 때마다(피드백 없이
바로 승인한 경우는 제외), `01_목차.md` 맨 위 `## 개정 이력` 섹션에
`- **YYYY-MM-DD**: <피드백 원문>` 한 줄이 자동으로 append됩니다.

- **요약 생성 없음**: 저자가 입력한 피드백 원문을 그대로(공백 정리만 하고, 200자
  넘으면 끝을 잘라) 기록합니다 — 새 LLM 호출을 추가하지 않았습니다.
- **`run_review_loop()`의 `on_feedback` 콜백**으로 라운드마다 실제로 개정을
  유발한 피드백만 수집합니다(`agents/review_loop.py`) — `models.py`의
  `append_toc_revision_entries()`가 그 목록을 받아 순수 문자열 조작으로 섹션을
  갱신합니다(마크다운을 다시 파싱하지 않고, 기존 `## 개정 이력` 섹션이 있으면
  이어붙이고 없으면 새로 만듭니다).
- **`build html`/`plan` 미리보기 등 다른 경로에 영향 없음**: 사이드바/챕터
  목록은 ` ```toc ` 코드 블록(`parse_toc_manifest`)만 파싱하므로, 그 위에
  붙는 `## 개정 이력` H2 헤딩은 빌드 파이프라인에 아무 영향을 주지 않습니다
  (실측: 개정 이력이 붙은 목차로 `book-forge build html`이 정상 동작함을 확인).

실측(실제 Ollama, `qwen3-coder:latest`): 임시 프로젝트를 만들어
`book-forge new`로 6챕터 목차를 승인한 뒤 `book-forge plan --revise`에서
"목차를 4개 챕터로 줄여줘"라고 피드백을 주니, 실제로 목차가 4챕터로 줄어들며
`01_목차.md` 맨 위에 `## 개정 이력\n- **2026-07-24**: 목차를 4개 챕터로
줄여줘`가 정확히 기록되는 것을 확인했습니다.

## 일반 능력 M — 챕터 구조 템플릿

Media/AOO 대비 품질 분석에서 나온 격차입니다: AOO의 모든 챕터는 "학습 목표 →
본문 → 핵심 요약" 틀을 공유하는데, Book-forge의 `DRAFT_PROMPT`는 지금까지
"`# Chapter N: 제목`으로 시작, `## `로 소제목만 나누라"는 최소 지시뿐이라
챕터마다 절 구성이 제각각이었습니다.

`agents/prompts.py`의 `DRAFT_PROMPT`(narrative)와 `DRAFT_PROMPT_EXERCISE`
둘 다에 고정 섹션 두 개를 추가했습니다 — 본문 시작에 `## 이 챕터에서 배우는
것`(2~3개 불릿), 본문 끝에 `## 이 챕터의 핵심`(3개 내외 불릿 요약). 기존
본문 지시(exercise의 `## 목표`/`## 실습`/`## 해설`)는 그대로 유지하고 그
앞뒤에만 새 섹션을 덧붙였습니다.

- **"대상 독자"/페르소나별 TIP 박스/"다음 챕터" 링크는 의도적으로 제외**했습니다
  — 대상 독자는 기획안 단계에서 이미 정해져 중복이고, 나머지 둘은 다권 전체의
  순서·페르소나 정보가 챕터 단위 프롬프트에 없어 프롬프트만으로 신뢰성 있게
  못 만듭니다(억지로 만들면 부정확한 "다음 챕터" 링크가 나올 위험 — 정직한
  스코프 축소).
- **강제 검증 없음**: `demonstration_verifier.py`는 이 두 섹션의 존재 여부를
  검사하지 않습니다 — 프롬프트 지시일 뿐, 모델이 100% 지킨다는 보장은 없습니다
  (알려진 한계로 아래 절에 기록).

실측(실제 Ollama, `qwen3-coder:latest`): `book-forge draft`로 챕터를 생성하니
`## 이 챕터에서 배우는 것`(3개 불릿)로 시작해 본문을 거쳐 `## 이 챕터의 핵심`
(3개 불릿)로 끝나는 걸 확인했습니다.

## 일반 능력 K — 소스 가중치 균형 조정

실전 6챕터 집필(`AI_에이전트_평가_입문` 프로젝트) 중 겪은 문제입니다:
`query_with_scores()`가 순수 코사인 유사도 top-k라, 파일 하나가 청크 수로
압도하면(실측: `quick_eval.py` 한 파일이 61%) 관련성과 무관하게 검색 결과를
지배합니다 — Chapter 3이 실제로 `metric_adapters.py`/`framework_integrations.py`
대신 `quick_eval.py`의 ANSI 터미널 색상 헬퍼 함수에 대해 생성됐습니다.

`KnowledgeStore.query_with_scores(text, top_k, *, max_per_source=None)`에
옵트인 파라미터를 추가했습니다 — 순위대로 훑으면서 한 소스(`# 파일:`/`# 출처:`
태그로 식별)가 `max_per_source`개를 넘으면 건너뛰고 다음 순위로 대체합니다.
`book-forge draft ... --max-per-source N`으로 노출됩니다(미지정 시 기존
동작 그대로).

- **선행 조건을 구현 중에 발견**: `sources.py`가 원래 파일 전체 앞에 태그를
  붙인 뒤 `chunk_text()`로 잘랐는데, 그러면 여러 청크로 쪼개지는 큰 파일은
  **첫 청크만** 태그를 갖습니다 — `max_per_source`가 정작 잡아야 할 대형
  파일의 나머지 청크를 식별하지 못해 무력화됩니다(실측: 위 재현 스크립트로
  `quick_eval.py`(195개 청크) 태그가 첫 청크에만 남는 걸 확인). `_tag_each_chunk()`로
  청킹 후 매 청크에 태그를 다시 붙이도록 `load_code_repo_source()`/`load_url_source()`를
  고쳤습니다 — 이 수정 없이는 K가 원래 겨냥한 사례(대형 파일)에서 정작 작동하지
  않았을 것입니다.
- **소스 식별은 파일 단위**: `max_per_source`는 `--source`로 지정한 인자
  단위가 아니라 태그가 가리키는 개별 파일/URL 단위로 작동합니다 —
  `--source ./agents`처럼 디렉토리를 하나 줘도 그 안의 파일마다 따로
  카운트됩니다(원래 실측 사례와 정확히 같은 단위).
- **태그 없는 청크는 통과**: PDF 등 태깅하지 않는 소스는 소스 식별이 안 되므로
  균형 조정 대상에서 제외되고 원래 순위 그대로 통과합니다(안전한 폴백).

실측(실제 Ollama 임베딩, agent_evaluator 자신의 `quick_eval.py`(195개
청크)/`metric_adapters.py`/`framework_integrations.py` 3개 파일로 재현):
`max_per_source` 없이는 top_k=8 결과 8개 전부가 `quick_eval.py`였습니다 —
`--max-per-source 2`를 주니 `quick_eval.py` 2개, `framework_integrations.py`
2개, `metric_adapters.py` 2개(총 6개, 남은 슬롯은 각 파일이 2개 상한에
걸려 채워지지 않음)로 정확히 분산됐습니다.

## 일반 능력 N — 리서치 에이전트 + 참고 자료 자동 인용

Media/AOO 대비 품질 분석에서 나온 가장 큰 격차입니다: AOO 콘텐츠는 실제 외부
리서치(설문조사·업계 리포트·논문)에 근거하고 참고 자료를 명시하는데,
Book-forge는 처음엔 저자가 직접 지정한 URL 1개를 가져올 뿐(A) "이 주제에
맞는 자료를 찾아온다"는 검색 단계가 없었습니다. 처음엔 범위를 좁혀 "저자가
이미 지정한 URL 중 실제로 쓰인 것만 인용 목록으로 조립"하는 것까지만
구현했다가, 이어서 검색 자동화(쿼리 생성 → 웹 검색 → 후보 URL 수집)까지
전체 범위로 확장했습니다.

### `book-forge research` — 검색 쿼리 생성 + 웹 검색

`book-forge research <slug> <chapter_no>`는 챕터 제목에서 검색 쿼리 2~3개를
LLM으로 생성하고(`agents/research_agent.py`), 각 쿼리로 실제 웹을 검색해
(`knowledge/web_search.py::search_web()`) 후보 URL(제목+요약)을 모읍니다.
후보 목록을 보여준 뒤 저자가 번호로 포함 여부를 직접 고르면(`--yes`로 전체
채택도 가능), 채택된 URL만 프로젝트 지식창고에 추가합니다.

- **검색 백엔드는 API 키 없는 DuckDuckGo HTML 엔드포인트**
  (`html.duckduckgo.com/html/`)를 `requests`로 직접 호출합니다 — Tavily
  같은 전용 검색 API 대신 이 방식을 고른 이유는 Book-forge의 "API 키 없이
  바로 시작할 수 있다" 원칙을 유지하기 위해서입니다. 대신 공식 API가 아니라
  결과 페이지를 파싱하는 방식이라 DuckDuckGo가 페이지 구조를 바꾸면 깨질 수
  있고, 과도한 호출은 일시 차단될 수 있습니다(알려진 한계).
- **신뢰도 자동 평가는 하지 않습니다**: 1차/2차 출처 분류 같은 판단은
  LLM에게 맡기지 않고, 저자가 제목/요약을 직접 훑어보고 포함 여부를
  고르는 것으로 대신합니다 — `book-forge plan`의 승인 루프와 같은 "최종
  판단은 저자" 원칙입니다.
- **`book-forge draft`가 `--source` 없이도 동작하도록 확장**했습니다 —
  `book-forge research`로 이미 채운 지식창고가 있으면 `--source`를 다시
  지정하지 않아도 그 지식창고로 바로 초안을 생성합니다(지식창고가 아예
  없는 프로젝트에서 `--source` 없이 부르는 건 기존처럼 에러).

실측(실제 DuckDuckGo + 실제 Ollama, `/tmp` 격리 환경): "비동기 프로그래밍이란?"
챕터로 `book-forge research`를 돌리니 실제 한국어 블로그·GitHub 소스 6개를
찾아 지식창고에 추가했고, 이어서 `book-forge draft ... `(`--source` 없이)로
생성한 챕터가 정상적으로 초안을 생성하며 실제로 인용된 3개 URL이 챕터 말미
`## 참고 자료`에 자동으로 나타나는 것까지 확인했습니다.

- **파서 버그를 실측으로 발견해 수정**: DuckDuckGo는 쿼리에 따라 결과 링크
  형식이 다릅니다 — 영어 쿼리에서는 리다이렉트 링크(`//duckduckgo.com/l/?uddg=...`)를,
  한국어 쿼리에서는 절대 URL을 그대로 줍니다. 리다이렉트 형식만 처리하도록
  짰다가, 실제 한국어 챕터 제목으로 돌려보고서야 결과가 통째로 0개로 나오는
  걸 발견해 두 형식 모두 처리하도록 고쳤습니다.

### 참고 자료 자동 인용(범위 축소판, 먼저 구현됨)

`--source`로 URL을 여러 개 지정하면(직접 지정하든 `book-forge research`가
채택했든), 챕터 생성 후 `query_with_scores()`가 실제로 top-k에 뽑은 청크 중
URL 소스(`# 출처:` 태그)만 중복 없이 순서대로 모아 챕터 말미에
`## 참고 자료` 섹션을 자동으로 붙입니다.

`--source`로 URL을 여러 개 지정하면, 챕터 생성 후 `query_with_scores()`가
실제로 top-k에 뽑은 청크 중 URL 소스(`# 출처:` 태그)만 중복 없이 순서대로
모아 챕터 말미에 `## 참고 자료` 섹션을 자동으로 붙입니다.

- **LLM이 만들지 않고 코드로 조립**: `draft_cmd.py`의 `_cited_url_sources()`가
  `scored`(검색 결과) 리스트에서 태그를 그대로 읽어 목록을 만듭니다 — LLM에게
  "출처를 나열해줘"라고 요청하지 않으므로, 존재하지 않는 출처를 지어내는
  환각 위험이 없습니다.
- **K의 태깅 수정이 이 기능의 전제 조건**: 매 청크에 태그를 다시 붙이도록
  고친 것(위 일반 능력 K) 덕분에, 여러 청크로 쪼개지는 긴 페이지도 인용
  누락 없이 전부 잡힙니다.
- **로컬 파일 소스만 쓴 경우 섹션이 안 붙습니다**: `--source`가 전부
  PDF/코드 저장소/텍스트 파일이면 URL 태그가 없어 `_cited_url_sources()`가
  빈 목록을 반환하고, `_append_references_section()`은 빈 목록이면 아무것도
  하지 않습니다(no-op).

## CLI 명령

| 명령 | 상태 | 설명 |
|---|---|---|
| `book-forge init` | ✅ | LLM Provider(Ollama/OpenAI/Anthropic) 및 API 키 설정 |
| `book-forge new <title> [--source ...] [--top-k] [--min-coverage] [--force] [--author] [--license-notice] [--edition] [--enable-llm-judge] [--judge-model]` | ✅ | 기획→목차 대화형 루프 + 스캐폴드 생성 (`--source` 주면 전체 챕터 자동 배치 초안까지). 같은 제목/슬러그의 기존 프로젝트가 있으면 덮어쓰기 전 확인(`--force`로 스킵). `--author`/`--license-notice`/`--edition`을 주면 HTML/PDF에 표지 페이지 자동 생성. `--enable-llm-judge`로 계측에 LLM 채점(faithfulness 등)을 옵트인 추가(OpenAI/Anthropic 키 필요, 기본 off) |
| `book-forge build html <slug> [--with-index]` | ✅ | 단일 HTML. `--with-index`로 책 끝에 찾아보기(색인) 섹션 추가(일반 능력 AL) |
| `book-forge build pdf <slug> [--chapter N] [--with-index]` | ✅ | 챕터별 PDF. `--with-index`로 `99_찾아보기.pdf` 추가 생성(`--chapter` 지정 시 무시) |
| `book-forge build epub <slug>` | ✅ | EPUB 3 전자책(zip, Playwright 불필요, 일반 능력 AJ). 실제 유통 채널 제출 전에는 `epubcheck`로 별도 검증 권장(이 프로젝트는 구조적 검증(zip 무결성 + well-formed XML)까지만 자동화) |
| `book-forge build slides <slug> [--chapter N] [--without-notes]` | ✅ | Reveal.js 발표자료 |
| `book-forge edit <slug> [--port] [--no-browser]` | ✅ | 웹 에디터 |
| `book-forge gate <slug> [--file] [--min-gate-score] [--gate-thresholds] [--golden-set] [--save-baseline] ...` | ✅ | Gate A-G 판정 (agent-eval gate 전체 플래그 통과). `--file` 미지정 시 챕터별 결과를 책 전체로 자동 집계 후 판정 |
| `book-forge draft <slug> <ch_no>\|--all [--source ...] [--top-k] [--min-coverage] [--max-per-source] [--yes] [--force] [--check-package] [--execute-examples] [--enable-llm-judge] [--judge-model]` | ✅ (선택, `[rag]`) | RAG 보조 챕터 초안/레퍼런스 표/다이어그램/실습·캡스톤 생성 (`--all`로 일괄, `--check-package`로 코드-본문 정합성 대조+버전 고정, `--execute-examples`로 실제 실행 검증 — 둘 다 로컬 디렉토리 대상도 지원. `--source`는 지식창고가 이미 있으면 생략 가능 — `book-forge research`로 미리 채워두면 됨. `--enable-llm-judge`는 `new`와 동일) |
| `book-forge research <slug> <chapter_no> [--max-queries] [--max-results-per-query] [--yes]` | ✅ (선택, `[rag]`) | 챕터 제목에서 검색 쿼리 생성(LLM) → 실제 웹 검색(DuckDuckGo) → 저자가 후보 URL 선택 → 지식창고에 추가 |
| `book-forge chat <slug> [--top-k N]` | ✅ (선택, `[rag]`) | 프로젝트 지식창고에 지속형 대화(ConversationSession) 질의 |
| `book-forge review <slug> <chapter_no>` | ✅ | 정확성/가독성 검토자 패널 + 편집장 종합 판정 (Gate F 실증, 일반 능력 G) |
| `book-forge lint <slug> [--fail-on-inconsistency]` | ✅ | 챕터 간 기술 용어 표기 불일치 후보 발견·보고(자동 수정 없음, 일반 능력 AK) |
| `book-forge home [slug]` | ✅ | 데이터/프로젝트 폴더 파일 탐색기로 열기 |
| `book-forge plan <slug> [--revise]` | ✅ | 기획/목차 재검토 — `--revise` 없으면 미리보기만 |
| `book-forge scaffold <slug>` | 🚧 | (현재 `new`/`plan --revise`에 통합됨 — 독립 실행 미구현) |
| `book-forge knowledge status <slug>` | ✅ | 지식창고 청크를 소스별(`# 파일:`/`# 출처:` 태그)로 집계해 보여줌 |
| `book-forge knowledge reset <slug> [--yes]` | ✅ | 지식창고(`knowledge/store.json`) 삭제 — RAG 캐시일 뿐 저작 콘텐츠는 영향 없음 |

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
│   ├── chapter_drafter.py # ChapterDrafterAgent — RAG 소스 → 챕터 초안 (narrative/exercise, rag_mode=True, 옵션)
│   ├── reference_table.py # ReferenceTableAgent — RAG 소스 → 레퍼런스 표 (B)
│   ├── diagram_generator.py # DiagramGeneratorAgent — RAG 소스 → Mermaid 다이어그램 (B)
│   ├── capstone_generator.py # CapstoneGeneratorAgent — 빈 템플릿+별도 정답 2파일 (B)
│   ├── alternative_suggester.py # AlternativeSuggesterAgent — 낮은 커버리지 → 대안 제안 (F)
│   ├── demonstration_verifier.py # 생성 후 정적 검증 — exercise 문법/diagram 구조/
│   │                       # reference_table 소스 대조/capstone TODO+완성도 (D, LLM 미호출 순수 함수)
│   ├── code_consistency_checker.py # 본문의 import/백틱 심볼이 실제 패키지에
│   │                       # 존재하는지 대조. 로컬 디렉토리 대상이면 code_index.py의
│   │                       # 정적 분석으로 자동 전환 (C 확장, I, LLM 미호출)
│   ├── sdk_version_pin.py # 프로젝트별 대상 버전 고정 + 드리프트 감지 —
│   │                       # 설치 패키지는 pip 버전, 로컬 디렉토리는 git 커밋 (C 확장, I, LLM 미호출)
│   ├── code_example_verifier.py # python 코드 블록을 subprocess로 실제 실행해
│   │                       # 검증. 로컬 대상이면 PYTHONPATH 자동 주입 (C 확장, I, --execute-examples 옵트인)
│   ├── chat_agent.py      # ChatAgent — 지식창고 기반 Q&A (E)
│   └── review_panel.py    # ReviewPanelAgent — 정확성/가독성 검토자 + 편집장
│                           # (G, 감독자-작업자 패턴 — Gate F 실증 예제)
├── knowledge/      # RAG — 소스 어댑터 + Ollama 임베딩 인메모리 코사인 유사도 검색 ([rag] extra)
│   ├── embeddings.py      # Ollama /api/embeddings, 컨텍스트 길이 초과 시 자동 축소 재시도
│   ├── store.py           # KnowledgeStore — numpy 코사인 유사도 + save/load/merge (E)
│   ├── sources.py         # 소스 어댑터 — PDF/코드 저장소/텍스트/URL 자동 판별 (A)
│   ├── code_index.py      # 구조적 코드 인덱싱 — ast 정적 분석으로 모듈/클래스/
│   │                       # 함수 인벤토리 + 내부/외부 의존 관계 추출 (H, LLM 미호출)
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

`book-forge gate <slug>`는 `--file`을 안 주면 `eval_results/`의 챕터별 결과
전부를 `PerformanceMonitor.merge()`(agent-evaluator 기존 기능, 새 판정 로직
아님)로 책 한 권 분량으로 집계한 뒤 agent-evaluator의 `agent-eval gate` CLI를
그대로 위임 호출합니다(일반 능력 AF) — 파일이 하나뿐이면 병합 없이 그대로
씁니다. 특정 챕터 하나만 다시 보고 싶으면 `--file`로 명시하세요.

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
- **`book-forge research`는 비공식 검색 경로에 의존**: DuckDuckGo의 공식 검색 API가
  아니라 API 키 없는 HTML 결과 페이지(`html.duckduckgo.com/html/`)를 파싱합니다 —
  DuckDuckGo가 페이지 구조를 바꾸면 파싱이 깨질 수 있고, 짧은 시간에 반복 호출하면
  일시적으로 결과가 차단될 수 있습니다. 신뢰도 평가(1차/2차 출처 구분 등)도 자동화하지
  않습니다 — 후보 목록을 저자가 직접 보고 채택 여부를 고릅니다.
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
- **챕터 구조 템플릿(일반 능력 M)은 강제되지 않습니다**: `## 이 챕터에서 배우는
  것`/`## 이 챕터의 핵심` 두 섹션은 프롬프트 지시일 뿐이라 `demonstration_verifier.py`가
  존재 여부를 검사하지 않습니다 — 소스가 아주 빈약한 챕터 등에서는 모델이 섹션을
  빠뜨리거나 형식을 살짝 바꿀 수 있습니다.
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
- **Ollama 추론("thinking") 모델은 `think=false`로 강제 억제합니다(실측 버그 수정 완료)**:
  `qwen3.6:35b-mlx` 같은 추론 모델은 `num_predict` 예산을 답변 전에 내부 사고 과정
  (`<thinking>`)에 다 써버릴 수 있는데, Ollama의 `/api/generate`는 이 사고 과정을
  `response`가 아니라 별도 `thinking` 필드에 담습니다 — `OllamaLLM.generate()`가
  `response`만 읽으므로, 예산을 다 쓰면(`done_reason="length"`) 챕터 파일이 통째로
  빈 채 저장되는 걸 실제 사용자 환경(`qwen3.6:35b-mlx`)에서 재현했습니다.
  `llm/provider.py`의 `OllamaLLM.generate()`가 페이로드에 `think: false`를 항상
  포함해 추론 모델도 사고 과정 없이 바로 답변하게 강제합니다 — 추론을 지원하지
  않는 모델(예: `qwen3-coder`)은 이 옵션을 그냥 무시합니다(실측 확인, 에러 없음).
- **URL 소스는 정적 HTML만 지원**: `--source https://...`는 표준 라이브러리
  `html.parser`로 `<script>/<style>/<head>`만 제거하고 나머지 텍스트를 그대로
  모읍니다(trafilatura/readability 같은 본문 추출 전용 라이브러리 미사용 — 의존성
  최소화 원칙). 네비게이션·푸터 등 잡음이 섞여 나올 수 있고, JS로 본문을 렌더링하는
  SPA 페이지는 텍스트를 거의 못 가져옵니다. 재귀적으로 링크를 따라가지 않고 지정한
  URL 1개만 가져오며, 리다이렉트/robots.txt는 별도로 존중하지 않으므로 저자 본인이
  권한이 있거나 공개된 자료만 지정하세요.
- **`--execute-examples`는 LLM이 생성한 코드를 실제로 실행합니다**: `subprocess`로
  격리하고 타임아웃을 걸지만, 컨테이너 수준의 파일시스템/네트워크 격리는 없습니다 —
  이 프로세스를 실행하는 사용자 권한 그대로 코드가 돌아갑니다. 생성된 코드는
  `--source`로 넣은 RAG 소스의 영향을 받으므로, 신뢰할 수 없는 출처(예: 검증되지
  않은 코드 저장소)를 소스로 쓸 때는 특히 주의하세요. 기본은 꺼져 있고
  (`--check-package`와 함께 명시적으로 켜야 함), 실행 실패는 경고만 하고 초안
  저장을 막지 않습니다.

## 개발

```bash
pip install -e ".[dev,pdf,serve,rag]"
playwright install chromium
pytest                 # 408개 테스트
ruff check src tests scripts
python -m build --wheel   # 패키징 검증 (editor/templates/*.html 포함 여부 확인 필수)
```

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
