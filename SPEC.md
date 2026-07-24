# Book-forge 개선 Spec — J~O (2026-07-24)

이 세션에서 실제로 두 유형의 강의를 만들어보며(AI Agent 강의, "AI 에이전트 평가 입문" 6챕터
실집필, Media/AOO 대비 품질 비교) 도출한 구조적·기능적 개선 요구사항이다. A–I는 이미 구현·
문서화 완료(README "일반 능력 A–I" 참고) — 이 Spec은 그 뒤를 잇는 J–O만 다룬다.

우선순위는 **비용 대비 가치**와 **기존 인프라 재사용 가능성** 기준으로 정렬했다:

```
L(코드 정합성 패키지 전체 스캔) → J(지식창고 라이프사이클) → O(목차 개정 이력)
  → M(챕터 구조 템플릿) → K(소스 가중치 균형) → N(리서치 에이전트+출처 인용)
```

---

## L. 코드-본문 정합성 검사의 패키지 전체 스캔

**문제**: `code_consistency_checker.py`의 설치된-패키지 모드는 `importlib.import_module(target_package)`
로 얻은 **최상위 네임스페이스**만 본다. 이번 세션 실전 테스트에서 `Settings`·
`KoreanRAGDatasetGenerator`·`LiveGuardrail` 세 번 모두 실제로 존재하는 클래스인데 최상위에
재노출 안 됐다는 이유만으로 "없음"으로 오탐이 났다(각각 `agent_evaluator.config`,
`agent_evaluator.datasets`, `agent_evaluator.gates.live_guardrail`에 실존).

**해법**: 로컬 모드(I)가 이미 `knowledge/code_index.py`의 정적 분석으로 "패키지 전체에서 이
심볼이 존재하는가"를 판정하는 방식을 만들어뒀다. 설치된 패키지 모드에도 같은 원리를
적용한다 — `pkgutil.walk_packages()`로 target_package의 서브모듈을 순회하며 각 모듈의
멤버를 모아 평평한 심볼 테이블을 만들고, 최상위에서 못 찾은 심볼은 이 테이블에서 재확인한다.

**요구사항**:
- 새 함수 `_walk_package_symbols(root_module) -> set[str]` — `pkgutil.walk_packages()`로
  target_package 산하 전체 서브모듈을 import하고 각 모듈의 공개 멤버(`_` 제외) 이름을 수집.
- `verify_code_consistency()`의 backtick 심볼 체크가 최상위(`_resolve_dotted`)에서 실패하면
  이 평평한 테이블로 재확인 — 재확인도 실패해야 최종 "없음"으로 판정.
- import 문(`from X import Y`) 체크는 이미 `importlib.import_module(module_path)`로 정확한
  서브모듈을 직접 import하므로 이 버그의 영향을 안 받는다 — **백틱 심볼 체크만** 해당.
- 서브모듈 import 실패(선택적 의존성 등)는 무시하고 건너뛴다 — 전체 스캔이 죽지 않게.
- 성능: 서브모듈 walk는 첫 호출 시 1회만 수행하고 캐시(모듈 레벨 `dict` 캐시, target_package별).

**수용 기준**:
- `Settings`/`KoreanRAGDatasetGenerator`/`LiveGuardrail`을 언급하는 챕터가 전부 정합성 검사를
  통과해야 한다(실측 재현 케이스를 오프라인 테스트로 고정).
- 진짜 존재하지 않는 심볼(`NonExistentThing` 등)은 여전히 정확히 잡아내야 한다(회귀 방지).

---

## J. 지식창고 라이프사이클 관리

**문제**: `KnowledgeStore.add()`는 중복 제거가 없다. 실전 테스트에서 소스를 재선정할 때마다
`knowledge/store.json`을 수동으로 `rm`해야 했다 — 잘못된 소스가 한 번 섞이면 이후 `--source`
목록에서 빼도 이미 임베딩된 청크가 store에 계속 남아 검색 결과를 오염시킨다(실측: OpenCode
플러그인 TS 파일이 3개 챕터 뒤까지 영향을 미침).

**요구사항**:
- `book-forge knowledge status <slug>` — 현재 store의 총 청크 수, 그리고 가능하면 청크 태그
  (`# 파일: xxx.py`/`# 출처: URL`)를 파싱해 소스별 청크 수 요약을 표로 출력.
- `book-forge knowledge reset <slug> [--yes]` — `knowledge/store.json`을 삭제(되돌릴 수 없음
  — 확인 프롬프트 필수, `--yes`로 스킵 가능). RAG 캐시일 뿐 저작 콘텐츠가 아니므로 삭제는
  안전하지만, 실수 방지를 위해 기본은 확인을 요구한다.
- 새 판정 로직 없음 — 기존 `KnowledgeStore.load()`/파일 삭제만 감싼 얇은 CLI 래퍼.

**수용 기준**:
- `status`가 청크 태그 파싱으로 소스별 분포를 정확히 보여준다(다중 소스로 만든 스토어에서
  검증).
- `reset --yes`가 파일을 삭제하고, 이후 `draft`가 빈 스토어에서 정상적으로 새로 시작한다.
- 확인 없이 `reset`을 호출하면(TTY에서) 취소할 수 있다.

---

## O. 목차 개정 이력 자동 기록

**문제**: `book-forge plan --revise`가 목차를 바꿀 때마다 이전 목차를 조용히 덮어쓴다. AOO의
목차 파일은 "2026-07-14 개정 ①/②/③"처럼 무엇을·왜 바꿨는지 날짜와 함께 누적 기록한다 —
Book-forge에는 이 개념이 전혀 없다.

**요구사항**:
- `01_목차.md` 파일 상단(``` ```toc ``` 블록 이전)에 `## 개정 이력` 섹션을 두고, `plan --revise`
  로 목차가 실제로 바뀔 때마다 `- **YYYY-MM-DD**: <저자가 입력한 수정 요청 요약>` 형태로 한
  줄 append.
- 새 판정 로직 없음 — 기존 `run_review_loop()`이 이미 받는 저자 피드백 텍스트를 그대로
  기록에 재사용한다(요약 생성 X, 원문 그대로 또는 앞부분만 자름).
- 목차가 실제로 바뀌지 않은 경우(피드백 없이 바로 승인) 기록하지 않는다.

**수용 기준**:
- `plan --revise`를 두 번 연속 다른 피드백으로 실행하면 목차 파일에 개정 이력 두 줄이
  날짜와 함께 누적된다.
- 최초 `new` 생성 시점에는 개정 이력 섹션이 비어있거나 없다(정상 — 처음 만든 것은 "개정"이
  아님).

---

## M. 챕터 구조 템플릿

**문제**: `DRAFT_PROMPT`(narrative)는 "`# Chapter N: 제목`으로 시작, `## `로 소제목만 나누라"는
최소 지시뿐이다 — AOO의 모든 챕터가 공유하는 "학습 목표 → 대상 독자 → 본문 → 핵심 요약 →
다음 챕터" 같은 일관된 틀이 없다. 실측: 방금 생성한 6챕터가 절 구성이 챕터마다 제각각이었다.

**요구사항**:
- `DRAFT_PROMPT`(및 `DRAFT_PROMPT_EXERCISE`)에 다음 고정 섹션을 요구하도록 프롬프트 수정:
  - `## 이 챕터에서 배우는 것` — 2~3개 불릿.
  - (본문, 기존과 동일)
  - `## 이 챕터의 핵심` — 3개 내외 불릿 요약.
- "대상 독자"/"다음 챕터" 링크/페르소나별 TIP 박스는 이번 범위에서 **제외** — 전자는
  기획안 단계에서 이미 정해진 대상 독자와 중복되고, 후자 둘은 다권 전체의 순서/페르소나
  정보가 챕터 단위 프롬프트에는 없어 프롬프트만으로 신뢰성 있게 못 만든다(솔직한 스코프
  축소 — 억지로 만들면 부정확한 "다음 챕터" 링크가 나올 위험).
- `demonstration_verifier.py`에 새 검증기 없음 — 구조 준수 여부는 Gate C(HallucinationDetector)
  범위 밖이라 강제하지 않는다(참고용 프롬프트 지시일 뿐, 필수 검증 대상 아님).

**수용 기준**:
- 실제 Ollama로 생성한 챕터가 "이 챕터에서 배우는 것"/"이 챕터의 핵심" 두 섹션을 포함하는지
  확인(형식 준수는 프롬프트 지시 수준 — 모델이 100% 안 지킬 수 있음을 알려진 한계로 문서화).

---

## K. 소스 가중치 균형 조정

**문제**: `query_with_scores()`가 순수 코사인 유사도 top-k라, 파일 하나가 청크 수로 압도하면
(실측: `quick_eval.py` 한 파일이 61%) 관련성과 무관하게 검색 결과를 지배한다.

**요구사항**:
- `KnowledgeStore.query_with_scores(text, top_k, *, max_per_source: int | None = None)` —
  청크 태그(`# 파일: xxx`/`# 출처: URL`)로 소스를 식별해, 한 소스가 top_k 결과의
  `max_per_source`개를 넘으면 그 이후 청크는 건너뛰고 다음 순위 청크로 대체.
- 기본값 `max_per_source=None`(기존 동작 그대로, 하위 호환) — `draft_cmd.py`가 opt-in으로
  `--max-per-source` CLI 옵션을 노출.
- 청크 태그가 없는 소스(태그를 안 남기는 어댑터가 미래에 추가될 경우)는 소스 식별 불가 시
  균형 조정 없이 원래 순위 그대로 통과(안전한 폴백).

**수용 기준**:
- 한 파일이 청크의 과반을 차지하는 인위적 테스트 스토어에서, `max_per_source=2` 지정 시
  top_k 결과에 그 파일 청크가 2개를 넘지 않음을 확인.
- `max_per_source` 미지정 시 기존 테스트가 전부 그대로 통과(회귀 없음).

---

## N. 리서치 에이전트 + 출처 인용 체계 (범위 축소판)

**문제**: AOO의 콘텐츠는 상당 부분이 로컬 소스가 아니라 실제 외부 리서치(설문조사·업계
리포트·논문, 1차/2차 출처 구분, 날짜·표본 수 명시)에 근거한다. Book-forge는 사용자가 직접
지정한 URL 1개만 가져올 뿐(A), "이 주제에 맞는 자료를 찾아온다"는 검색 단계 자체가 없다.

**범위 축소 이유**: 진짜 웹 검색 통합(자동 쿼리 생성 → 다건 검색 → 신뢰도 평가)은 이
Spec의 다른 항목보다 훨씬 크고, API 키/외부 서비스 의존성 문제가 얽힌다. 이번 라운드는
**저자가 이미 찾아둔 여러 URL을 근거로, 문장 단위 출처 인용을 자동 생성하는 것**까지만
다룬다 — "검색"은 저자 몫으로 남기고 "인용 관리"부터 자동화한다. 진짜 검색 자동화는 별도
후속 항목으로 미룬다.

**요구사항**:
- `--source`로 URL을 여러 개(예: 5~10개) 주면, 각 URL의 청크에 이미 `# 출처: {url}` 태그가
  붙어 있다(기존 A). 이 태그를 활용해 챕터 생성 시 실제로 인용된 소스 URL 목록을
  `query_with_scores()`의 결과에서 추출한다.
- 챕터 생성 후 draft_cmd.py가 사용된 출처 URL만 모아 챕터 말미에 `## 참고 자료` 섹션을
  자동 append(LLM이 만드는 게 아니라 draft_cmd.py가 코드로 조립 — 환각 방지).
- LLM에게는 "출처를 조작하지 말고, 안다면 어느 소스에서 나온 정보인지 프롬프트에 알려진
  출처 URL만 언급하라"는 지시를 추가(선택적 강화, 검증은 안 함 — C의 기존 커버리지 점검이
  이미 이 역할의 일부를 함).

**수용 기준**:
- URL 소스 여러 개로 챕터를 생성하면, 실제로 top-k에 뽑힌 청크들의 출처 URL이 중복 없이
  챕터 말미에 나열된다.
- 코드 URL이 아닌 로컬 파일 소스만 쓴 경우 "참고 자료" 섹션이 안 붙는다(URL 소스가 하나도
  없으면 스킵).

---

## N(추가) — 리서치 에이전트 전체 범위 (2026-07-24 확장)

위 N 항목 완료 후, 범위 축소 사유였던 "진짜 검색 자동화"까지 이어서 구현했다.

**요구사항(추가분)**:
- 챕터 제목 → 검색 쿼리 2~3개 생성(LLM, `agents/research_agent.py`).
- 생성된 쿼리로 실제 웹 검색을 수행해 후보 URL(제목+요약)을 수집
  (`knowledge/web_search.py::search_web()`).
- 검색 백엔드는 API 키가 필요 없는 DuckDuckGo HTML 엔드포인트
  (`html.duckduckgo.com/html/`)를 `requests`로 직접 호출 — Tavily 등 유료/키
  필요 API 대신 선택(Book-forge의 "API 키 없이 바로 시작" 원칙 유지, 사용자
  확인 후 결정).
- 신뢰도 자동 평가(1차/2차 출처 분류 등)는 **포함하지 않는다** — 저자가
  후보 목록(제목/요약/URL)을 직접 보고 포함 여부를 고르는 것으로 대신한다
  (`book-forge research`의 대화형 선택 프롬프트). LLM이 안정적으로 못 하는
  판단을 자동화하기보다 사람이 최종 판단하는 게 기존 승인 루프(plan/toc)
  원칙과 일관된다는 판단.
- 채택된 URL은 기존 `collect_sources_into_store()`(draft_cmd.py)를 재사용해
  지식창고에 추가 — 새 저장 로직 없음.
- `book-forge draft`가 `--source` 없이도(연구로 이미 채운 지식창고만으로)
  동작하도록 완화 — 지식창고가 아예 비어있을 때만 기존처럼 에러.

**수용 기준**:
- `book-forge research <slug> <chapter_no>`가 실제로 웹을 검색해 후보 URL
  목록을 보여주고, 저자가 고른 것만 지식창고에 추가한다.
- 이후 `book-forge draft <slug> <chapter_no>`를 `--source` 없이 실행해도
  방금 채운 지식창고로 정상 초안이 생성된다.
- 실제로 인용된 URL이 챕터 말미 `## 참고 자료`에 자동으로 나타난다(위 N
  범위 축소판과 자연스럽게 이어짐).

상세 근거·실측 결과는 CLAUDE.md 항목 30 참고.

---

# Book-forge 개선 Spec 2부 — P~U (2026-07-24, "프로젝트 코드 → 도서/강의자료" 격차)

Book-forge 자신의 `src/book_forge/agents/`를 실제 입력으로 삼아 `new`→`draft`→
`build html/slides` 전 과정을 직접 돌려보고 발견한 격차다(코드 읽기만으로는
드러나지 않던 것들 — 실측으로 확인). H(구조적 코드 인덱싱)/I(로컬 코드베이스
대상 검증)가 이미 있는 상태에서 "그 위에 무엇이 더 필요한가"를 다룬다.

## P. 슬라이드가 코드 블록을 전부 버림

**문제**: `slide_condenser.py`의 `condense_section()`이 섹션 전체(코드 블록 포함)를
그대로 LLM에 넘겨 프로즈 요약을 시킨다. 실측: 코드 예제 4개가 있는 챕터로
슬라이드를 만들었더니 결과 HTML에 `<pre>`/`<code>` 태그가 **0개** — 코드가
전부 "RESEARCH_QUERY_SYSTEM_PROMPT은 챕터 제목 기반 검색 쿼리 생성" 같은
추상적 문장으로 바뀌었다. 코드 워크스루가 핵심인 강의자료에서 치명적이다.

**해법**: `extract_code_blocks()`로 코드/mermaid 펜스를 LLM에 넘기기 전에 미리
뽑아내고, 프로즈만 조건 요약한 뒤 뽑아낸 코드는 원문 그대로 별도 슬라이드로
붙인다(LLM 미호출, 환각 위험 없음).

**상태**: ✅ 완료 (CLAUDE.md 항목 31)

## Q. 슬라이드 HTML에 Mermaid.js/highlight.js가 로드 안 됨

**문제**: `html_builder.py`(도서)는 CDN으로 mermaid.js/highlight.js를 로드하는데
`slide_builder.py`(발표자료)는 reveal.js 코어만 로드했다 — 코드/다이어그램이
슬라이드에 살아남아도 렌더링될 수 없었다.

**해법**: `html_builder.py`와 같은 CDN·버전·초기화 방식을 `REVEAL_HEAD`/
`REVEAL_FOOTER`에 그대로 맞췄다.

**상태**: ✅ 완료 (CLAUDE.md 항목 31, P와 같은 커밋)

## R. 다이어그램 챕터로 슬라이드를 만들면 통째로 0장 생성됨(실제 버그)

**문제**: `split_chapter_into_sections()`는 `# `/`## ` 헤딩이 하나도 없으면
섹션을 하나도 못 찾는다. 실측 재현: diagram content_type 챕터가 헤딩 없이
` ```mermaid `로 바로 시작하자 슬라이드가 조용히 0장 생성됐다(에러 없이
낮은 가시성의 경고 한 줄만 — `generate_report() called with no recorded tasks`).

**해법**: 헤딩이 전혀 없어도 본문이 있으면 챕터 제목(`fallback_heading`)을
헤딩 삼아 최소 1개 섹션은 만들도록 폴백을 추가했다.

**상태**: ✅ 완료 (CLAUDE.md 항목 31, P/Q와 같은 커밋)

## S. 기획/목차 설계가 코드 구조를 전혀 못 봄

**문제**: `propose_plan()`/`design_toc()`는 저자가 타이핑한 자유 텍스트만 받고,
`--source`는 목차 확정 **이후** draft 단계에서만 쓰인다. 실측: "Book-forge의
agents 패키지 구조를 분석"이라는 제약으로 목차를 만들었더니, 실제로는 존재
하지 않는 "에이전트 컴포넌트 간 상호작용 및 통신 메커니즘", "성능 최적화
전략" 같은 챕터가 만들어졌다(실제 `agents/`는 독립적인 LLM 호출 함수들의
모음일 뿐, 그런 서브시스템이 없음). H가 이미 정확한 모듈 인벤토리를
파싱해두고도 기획/목차 단계에 전혀 연결돼 있지 않다.

**해법**: `book-forge new --source <코드 저장소>`를 줬을 때, 목차 설계
**이전**에 H(`build_structure_index`+`format_structure_summary`, 새 파싱
로직 없이 기존 인프라 재사용)로 구조 요약을 미리 만들어 `TOC_PROMPT`에
"실제 발견된 모듈/클래스 목록" 컨텍스트로 추가한다. `--source`가 PDF/URL
같은 비-코드 소스거나 지정 안 하면 기존 동작 그대로(하위 호환).

**상태**: ✅ 완료 (CLAUDE.md 항목 34). 실측(동일 "Book-forge agents 패키지
분석" 시나리오 재현, `--source`를 `new` 시점부터 지정): 목차가
"챕터 5. 챕터 초안 작성자 (chapter_drafter.py)", "챕터 7. 코드 일관성
검증기 (code_consistency_checker.py)"처럼 실제 파일명을 직접 챕터
제목으로 인용하는 수준으로 바뀌었다 — 이전엔 존재하지 않던 "컴포넌트 간
통신 메커니즘" 같은 챕터가 완전히 사라졌다.

## T. "전체를 다룬다"는 보장이 없음 — 임베딩 유사도 운에 좌우

**문제**: draft 단계에서 RAG가 우연히 정확한 내용을 가져오더라도(실측: agents
13개 파일 중 4개는 정확히 설명), top_k 유사도 검색이라 나머지 9개는 그냥
누락된다. H가 이미 전체 모듈의 완전한 목록을 갖고 있는데도, "모든 X를
빠짐없이 다루는" 레퍼런스형 콘텐츠를 만드는 체계적 메커니즘이 없다.

**해법**: `reference_table`처럼 content_type을 하나 더 추가(`module_reference`
후보) — RAG 청크 검색 대신 H의 `ModuleSummary` 목록을 그대로 순회해 표/목록을
조립한다(LLM은 각 항목의 설명 문구만 채우고, 어떤 모듈이 존재하는지는 코드가
결정 — reference_table.py가 소스 발췌문 대조로 날조를 막는 것과 같은 원칙).

**상태**: ✅ 완료 (CLAUDE.md 항목 32). 실측(agents/ 13개 파일 재현): 44개
항목(클래스+함수)을 전부 결정론적으로 나열했고, LLM이 그중 16개를 표에서
빠뜨렸지만 `verify_module_reference_coverage()`가 정확히 어떤 항목이
빠졌는지 CLI에 즉시 보고했다 — "조용히 누락"에서 "빠짐없이 나열 + 누락
시 명시적 보고"로 바뀐 것이 T의 실질적 성과(LLM이 100% 완벽하게 표를
채우는 것까지는 보장 못 함, 그건 애초에 이 항목의 목표가 아니었음).

## U. 다이어그램이 실제 코드 구조를 보장하지 않음

**문제**: 다이어그램은 100% LLM이 RAG 텍스트 조각에서 재구성한 것이라, H가
이미 정적 분석으로 뽑아둔 정확한 import/의존 관계를 전혀 활용하지 않는다.
실측: "패키지 구조" 다이어그램을 요청했는데 파일 1개(`planner.py`)의 내부
데코레이터 관계만 그려졌다(로컬로는 정확하지만 스코프가 틀림). 검증
(`demonstration_verifier.py`)도 mermaid 문법만 보지, 실제 코드 관계와
일치하는지는 확인 안 한다.

**해법(실제 구현은 계획과 살짝 다름)**: 처음엔 "코드로 노드/엣지를 직접
조립"까지 생각했으나, T와 완전히 같은 인프라(H의 구조 요약 텍스트, "내부
의존:"/"외부 의존:" 표기 포함)를 diagram content_type에도 그대로 재사용하는
쪽이 더 간단하고 T와 일관됐다 — `_build_structure_summary_from_sources()`를
T/U가 공유. LLM에게 "정적 분석 표기가 있으면 그 관계를 그대로 옮기라"고
프롬프트로 지시하고, 사후 검증(`verify_diagram`)에 그래프 노드 라벨의
식별자가 실제 소스(구조 요약이든 RAG든)에 등장하는 비율을 확인하는
그라운딩 체크를 추가했다(reference_table.py의 "값이 소스에 있는가" 원칙
재사용, 옵트인 — sources_text 없으면 기존 동작 그대로).

**상태**: ✅ 완료 (CLAUDE.md 항목 33). 실측(agents/ 13개 파일 재현): "패키지
구조" 다이어그램 요청이 파일 1개(planner.py)의 내부 관계만 그리던 것에서,
19개 파일 전체를 아우르는 정확한 모듈 의존 그래프로 개선됐다(각 파일의
실제 import 문과 일치 확인).

## 부수 발견 (별도 항목 아님)

`code_example_verifier.py`가 `subprocess.run(capture_output=True)`로 stdout을
캡처하지만, 성공 시 그 출력을 완전히 버린다 — "이 코드를 실행하면 이런
결과가 나옵니다" 같은 실증 증거로 재활용하지 않는다. 낮은 우선순위(별도
문항으로 만들 만큼 크지 않음), 향후 T/U 작업 중 여유가 있으면 같이 본다.

---

## 구현 순서 및 상태 (전체)

| 항목 | 상태 |
|---|---|
| L | ✅ 완료 (CLAUDE.md 항목 24) |
| J | ✅ 완료 (CLAUDE.md 항목 25) |
| O | ✅ 완료 (CLAUDE.md 항목 26) |
| M | ✅ 완료 (CLAUDE.md 항목 27) |
| K | ✅ 완료 (CLAUDE.md 항목 28 — 구현 중 sources.py 태깅 선행 버그도 함께 수정) |
| N | ✅ 완료 (CLAUDE.md 항목 29, 범위 축소판) |
| N(추가) | ✅ 완료 (CLAUDE.md 항목 30 — 리서치 에이전트 전체 범위: 자동 쿼리 생성+웹 검색+`book-forge research`) |
| P | ✅ 완료 (CLAUDE.md 항목 31 — 슬라이드 코드 블록 보존) |
| Q | ✅ 완료 (CLAUDE.md 항목 31 — 슬라이드 렌더링 자산 로드) |
| R | ✅ 완료 (CLAUDE.md 항목 31 — 다이어그램 챕터 슬라이드 0장 버그) |
| S | ✅ 완료 (CLAUDE.md 항목 34 — 코드 구조 기반 목차 설계) |
| T | ✅ 완료 (CLAUDE.md 항목 32 — 구조 인덱스 기반 레퍼런스 커버리지) |
| U | ✅ 완료 (CLAUDE.md 항목 33 — 다이어그램 생성에 구조 데이터 활용) |

# Book-forge 개선 Spec 3부 — V~AE (2026-07-24, Media/Book·Lecture_forge 비교)

두 개의 별도 비교 분석에서 도출했다:
1. **Media/Book 비교**(`~/Projects/Agent-Evaluator/Media/Book/`, `build_book.py` 2415줄/
   `build_pdf_chapters.py` 1189줄) — "Book-forge로 이 정도 완성도의 산출물(HTML/PDF)을
   만들 수 있는가"를 코드 대 코드로 대조.
2. **Lecture_forge 비교**(`~/Projects/Lecture_forge/`, v0.6.3·PyPI 배포·1,892개 테스트) —
   같은 저자의 선행 프로젝트 대비 Book-forge의 파이프라인 성숙도가 어디서 뒤처지는지 대조.

두 비교 모두 실제 소스 코드를 직접 읽고 나온 결과이며, 실측(생성 테스트)까지 곁들인
항목은 각 항목에 명시한다. 우선순위는 기존 원칙(비용 대비 가치, 기존 인프라 재사용
가능성)을 그대로 따른다:

```
V(HTML 검색+스크롤스파이) → X(PDF 넓은 표 축소) → W(커스텀 컴포넌트 CSS)
  → AA(Part 서문 자동 생성) → Y(챕터 내 읽기 가이드) → Z(챕터 전용 예제 파일)
  → AD(RAG 계층 분리) → AB(생성물 자기검토 루프) → AC(품질 기반 자동 재작성)
  → AE(이미지 자동 배치)
```

---

## V. HTML 빌드에 본문 검색·스크롤스파이가 없음

**문제**(Media/Book 비교): Book-forge의 `html_builder.py`는 107줄, Media/Book의
`HTML_HEAD` 상수 하나만 1,190줄이다. 그 차이의 핵심은 **본문 전체 검색**(검색창 +
이전/다음 결과 탐색 + `<mark>` 하이라이트, 순수 JS)과 **스크롤 위치 기반 사이드바
active-link 자동 추적**(`IntersectionObserver`)이다 — 둘 다 서버/LLM 호출 없이 순수
프론트엔드 JS로 완결되는 기능이라 Book-forge에 이식하는 데 새 인프라가 필요 없다.

**해법**: `html_builder.py`의 `HTML_HEAD`/`HTML_FOOT`에 Media/Book의 검색 JS(정규식
매칭 → `TreeWalker`로 텍스트 노드 순회 → `<mark class="search-hit">` 삽입, prev/next
버튼)와 스크롤스파이 JS를 그대로 이식한다(로직 자체가 이미 검증된 완성품이라 재작성이
아니라 이식). `@media print`에서 검색창을 숨기는 것도 그대로 가져온다(PDF에는 불필요).

**우선순위**: 최우선(가장 저비용·고가치 — 순수 프론트엔드, LLM/Gate 리스크 전무).

**상태**: 계획

## W. 커스텀 비주얼 컴포넌트(카드/경고 박스) CSS가 없어 마이그레이션 콘텐츠가 깨짐

**문제**(Media/Book 비교): Media/Book 챕터는 `@@HTML_START@@/@@HTML_END@@` 블록
안에 `hc-card`(하네스 연결 카드), `gw-box`(경고 박스), `hc-chip`(태그 목록) 같은
커스텀 CSS 클래스를 쓴다. Book-forge의 `markdown_engine.py`는 이 블록 자체는
그대로 통과시키지만(`@@HTML_START@@` 보존 메커니즘 확인됨), 대응하는 CSS 정의가
전혀 없다. 실측: `scripts/migrate_legacy_book.py`를 읽어보니 마크다운 콘텐츠만
옮기고 CSS는 포팅하지 않는다 — **지금 마이그레이션하면 이런 카드/박스가 스타일
없이 밋밋한 HTML로 깨져 보인다.**

**해법**: Media/Book의 `HTML_HEAD`에서 `hc-*`/`gw-*` 클래스 정의만 추출해
`html_builder.py`의 CSS에 옵트인 섹션으로 추가한다(항상 켜두면 사용 안 해도
CSS 용량만 늘어나지만, 실제로 이런 블록이 없으면 렌더링에 영향 없음 — 안전).
`scripts/migrate_legacy_book.py`가 이 CSS를 자동으로 함께 포팅하도록 확장하는
것도 함께 고려(마이그레이션 명령 하나로 완결되게).

**우선순위**: 상(마이그레이션 콘텐츠의 실제 렌더링 손상을 막는 항목이라 W 단독으로도
가치가 있고, V와 같은 `html_builder.py` 작업이라 묶어서 처리하면 효율적).

**상태**: 계획

## X. PDF에서 넓은 표가 페이지 폭에 맞게 축소되지 않음

**문제**(Media/Book 비교): Media/Book의 `build_pdf_chapters.py`는 JS로
`.table-scale-wrap` + `transform: scale(N)`을 주입해 넓은 표를 페이지 폭에 맞게
동적으로 축소한다. Book-forge README에는 이미 "매우 큰 다이어그램은 페이지
경계에서 잘릴 수 있다"는 한계가 명시돼 있는데, **표에도 같은 위험이 있다** — 지금
확인하지 않은 gap.

**해법**: Media/Book의 표 축소 JS(테이블 실제 렌더링 폭을 측정해 페이지 폭을
넘으면 `transform: scale()` 비율을 계산해 적용)를 `pdf_builder.py`의 빌드 시점
주입 스크립트로 그대로 이식한다. `_PDF_OVERRIDE_CSS`의 표 관련 규칙(`word-break`,
`font-size: 8.5pt` 축소 등)도 함께 가져온다.

**우선순위**: 상(V/W와 함께 "산출물 완성도" 묶음, 저비용).

**상태**: 계획

## Y. 챕터 내부에 독자별 읽기 가이드·상호 참조가 없음

**문제**(Media/Book 비교): Media/Book 챕터마다 서두에 "QA 관리자는 §4.1→§4.4→§4.5,
개발자는 §4.2→§4.3→§4.4" 같은 절 단위 읽기 경로와, 다른 Appendix/예제 파일로의
"관련 레퍼런스" 링크 블록이 있다. Book-forge의 M(챕터 구조 템플릿)은 "이 챕터에서
배우는 것"/"이 챕터의 핵심"만 있고, 이런 절 단위 세밀한 안내나 상호 참조 자동
생성은 없다.

**해법**: `DRAFT_PROMPT`에 선택적 섹션을 추가 — 대상 독자가 기획안에 여럿 명시된
경우(`00_기획안.md`의 "대상 독자" 필드에서 파싱), "## 독자별 읽기 가이드" 절을
요청한다. "관련 레퍼런스" 링크는 LLM에게 맡기면 존재하지 않는 파일을 지어낼
위험이 크므로(M 항목에서 "다음 챕터" 링크를 의도적으로 뺀 것과 같은 이유),
LLM 생성 대신 `01_목차.md`의 실제 챕터 목록에서 코드로 관련 챕터를 골라 붙이는
방식을 검토(예: 같은 Part 내 다른 챕터, 또는 reference_table/module_reference
유형 챕터로 자동 링크).

**우선순위**: 중(콘텐츠 프롬프트 확장 + 약간의 코드 조립, M의 자연스러운 확장).

**상태**: 계획

## Z. 챕터 전용 독립 실행 예제 파일이 없음

**문제**(Media/Book 비교, Lecture_forge에는 해당 기능 없음 — Media/Book만의 특징):
Media/Book은 `Evaluator_Examples/ch04_group_a.py` 같은 챕터별 독립 실행 스크립트를
본문과 별도 산출물로 갖고 있다. Book-forge의 `--execute-examples`는 챕터 "본문
안"의 코드 블록을 검증만 할 뿐, 독립 실행 가능한 companion `.py` 파일을 별도
산출물로 만들어내지 않는다(이전 세션의 AOO 비교로 도출했던 격차와 같은 결 — 아직
미해결).

**해법**: `exercise`/`capstone` content_type 챕터에 한해(코드가 확실히 있는
유형), `draft_cmd.py`가 본문에서 추출한 python 코드 블록을 하나로 이어붙여
`Examples/ch{N}_{slug}.py` 사이드카 파일로 저장하는 옵트인 플래그(`--save-examples`
후보)를 추가한다. `--execute-examples`가 이미 코드 블록을 추출·실행하는 로직을
갖고 있으므로(`code_example_verifier.py`) 그 추출 결과를 재사용 — 새 파싱 로직
없음.

**우선순위**: 중(명확한 스코프, 기존 `code_example_verifier.py` 재사용 가능).

**상태**: 계획

## AA. Part 서문 파일이 자동 생성되지 않음

**문제**(Media/Book 비교): Media/Book은 Part마다 `00_파트_서문.md`가 따로 있어
그 Part 전체의 문제의식·리스크 레지스터 등을 소개한다(예: `Part_VI_실전이식가이드/
00_파트_서문.md`, `Part_VII_실시간가드레일/00_파트_서문.md`). Book-forge의
스캐폴딩(`scaffold.py`)은 챕터 파일만 만들고 Part 서문 파일은 생성하지 않는다.

**해법**: `TOCDesignerAgent`가 설계한 목차에서 Part別로 소속 챕터 제목들을 모아
LLM에게 "이 Part가 다루는 범위를 2~3문단으로 소개하라"는 짧은 프롬프트를 추가
호출(챕터 생성과 별개, `scaffold_project()` 시점에 Part당 1회)하거나, 더 저렴하게
LLM 호출 없이 "이 Part는 다음 챕터들을 다룹니다: ..." 형태의 목차 나열만 자동
생성하는 옵션도 검토(옵트인 `--part-intro` 플래그 후보).

**우선순위**: 중(스캐폴딩 확장, LLM 호출 추가 여부는 구현 시 결정).

**상태**: 계획

## AB. 생성물이 스스로를 재검토해 고치는 자기검토 루프가 없음

**문제**(Lecture_forge 비교): Lecture_forge는 "RMC 자기검토" — CurriculumDesigner가
섹션 순서·학습목표 커버리지를 스스로 검증·수정하고, ContentWriter가 개념 비약/
설명 모호성을, QAAgent가 "각 주장을 소스 컨텍스트와 대조 → 할루시네이션 항목
제거"까지 자동으로 한다(2단계 self-reflection: Layer 1 검토 + Layer 2가 그 검토를
다시 검토). Book-forge는 생성 후 정적 검증(`demonstration_verifier.py`)까지는
있지만, **검증 결과를 보고 LLM이 스스로 고쳐 쓰는 루프는 없다** — 저자가 낮은
Gate 점수를 보고 수동으로 `--force` 재생성하는 게 전부다.

**해법(범위를 의도적으로 좁혀야 함 — N/N(추가)와 같은 패턴)**: 전체 RMC 수준(다단계
self-reflection)을 한 번에 구현하지 않고, 이미 있는 신호(Gate C/D 경고,
`demonstration_verifier.py`의 `issues` 리스트)를 저자 승인 없이 자동으로 1회
재작성에 활용하는 것부터 시작한다 — `review_loop.py`의 기존 `REVISE_PROMPT`
인프라(피드백을 반영해 개정)를 재사용해, "저자 피드백" 대신 "검증기가 찾은
문제 목록"을 자동으로 넣어 1회 재생성하는 옵트인 플래그(`--auto-fix` 후보).
완전한 다단계 self-reflection은 별도 후속 항목으로 미룬다.

**우선순위**: 하(가장 아키텍처적으로 크고, 잘못 설계하면 무한 재작성 루프·비용
폭증 위험 — LoopDetectionConfig 같은 안전장치 설계가 선행돼야 함).

**상태**: 계획

## AC. 품질 평가 결과를 바탕으로 한 자동 재작성 계획 수립이 없음

**문제**(Lecture_forge 비교): Lecture_forge의 `quality/evaluator.py` +
`revision_planner.py`는 "무엇이 부족한지 평가 → 어떻게 고칠지 계획 → 재생성"까지
짝을 이뤄 자동화돼 있고, 품질 기준 미달 시 최대 3회 자동 수정한다. Book-forge의
Gate C/D 경고는 참고용 신호만 내고 자동 재작성으로 이어지지 않는다.

**해법**: AB가 선행돼야 의미가 있다(자동 재작성 자체가 없으면 "몇 번 반복할지"도
무의미) — AB의 `--auto-fix`가 구현된 뒤, 재시도 횟수 상한(Lecture_forge의 "최대
3회"를 참고)과 각 시도의 Gate 점수를 비교해 더 나빠지면 이전 버전으로 롤백하는
안전장치를 추가하는 형태로 AB에 이어 붙인다 — 별도 신규 파이프라인이 아니라
AB의 확장.

**우선순위**: 하(AB 의존, AB보다 먼저 구현할 이유 없음).

**상태**: 계획

## AD. RAG 인프라가 계층 분리 없이 단일 파일에 몰려 있고 캐싱·듀얼쿼리가 없음

**문제**(Lecture_forge 비교): Lecture_forge는 `chunker.py`/`embeddings.py`/
`retriever.py`/`vector_store.py` 4개 파일로 RAG 책임이 나뉘어 있고, ChromaDB(진짜
벡터 DB), 15+15 듀얼 쿼리 검색(다국어), 쿼리 캐싱(동일 질문 60% 빠른 응답)까지
있다. Book-forge는 `knowledge/store.py` 단일 파일(~90줄, numpy 인메모리)이다 —
다만 이는 Book-forge가 처음부터 "벡터 DB 프로세스 없이 numpy로 충분한 규모"라고
**의도적으로 선택**한 설계라는 점을 감안해야 한다(store.py 자체 docstring에 명시).

**해법(전면 재작성이 아니라 선택적 보강)**: 아키텍처를 통째로 ChromaDB로 바꾸는
건 Book-forge의 "별도 프로세스/스키마 없이 로컬 파일 하나로" 원칙과 정면으로
배치되므로 권장하지 않는다. 대신 **저비용으로 얻을 수 있는 것만** 취한다:
쿼리 캐싱(같은 챕터 제목으로 반복 `--force` 재생성 시 임베딩 재계산 생략,
`functools.lru_cache` 수준으로 충분)만 먼저 검토하고, 듀얼쿼리/벡터 DB 교체는
"필요성이 실측으로 확인되면"으로 미룬다.

**우선순위**: 하(현재 규모에서 실측으로 확인된 성능 문제가 아직 없음 — 선제적
아키텍처 변경보다 실제 병목이 보일 때 대응).

**상태**: 계획(캐싱만 저비용 후속 검토 대상, 나머지는 보류)

## AE. 이미지 자동 배치·대안 검색이 없음

**문제**(Lecture_forge 비교): Lecture_forge는 RAG 컨텍스트 기반으로 이미지를
본문의 적절한 위치에 자동 배치하고(+750% 활용률 명시), 생성된 강의의 이미지를
대화형으로 삭제/교체하며 벡터 DB 기반으로 대안 이미지를 검색한다. Book-forge는
저자가 마크다운에 `![alt](./images/xxx.png)`를 수동으로 삽입하는 방식뿐이다.

**해법**: 범위가 크고(이미지 수집·매칭·대안 검색까지 필요) Book-forge의 핵심
가치(코드/구조 분석 기반 저술)와 거리가 있어, 이번 우선순위에서는 가장 낮게
둔다. 향후 필요성이 확인되면 별도 Spec 라운드로 다룬다.

**우선순위**: 최하(범위가 가장 크고 Book-forge의 핵심 가치와 거리가 있음 —
구현 여부 자체를 재검토 대상으로 남겨둔다).

**상태**: 보류(계획 없음, 재검토 대상)

---

## 구현 순서 및 상태 (3부)

| 항목 | 상태 |
|---|---|
| V | 계획 — HTML 검색+스크롤스파이 |
| W | 계획 — 커스텀 비주얼 컴포넌트 CSS |
| X | 계획 — PDF 넓은 표 자동 축소 |
| Y | 계획 — 챕터 내 독자별 읽기 가이드+상호 참조 |
| Z | 계획 — 챕터 전용 독립 실행 예제 파일 |
| AA | 계획 — Part 서문 자동 생성 |
| AB | 계획 — 생성물 자기검토 루프(범위 축소판, --auto-fix) |
| AC | 계획 — 품질 기반 자동 재작성(AB 확장) |
| AD | 계획(캐싱만 저비용 후속 검토, 나머지 보류) — RAG 계층 분리 |
| AE | 보류 — 이미지 자동 배치·대안 검색 |

# Book-forge 개선 Spec 4부 — AF~AL (2026-07-24, 전 과정 분석 + "실제 출판 가능한 도서" 요건)

주제 입력 → 소스 수집 → 기획/목차 → 집필 → Config 배선 → `book-forge gate` 최종
판정까지 **파이프라인 전체**를 코드로 추적한 결과(AF~AH)와, "실제 서점에 낼 수
있는 기술 서적"이라면 최소한 갖춰야 할 산출물 요건을 Book-forge의 현재 퍼블리싱
계층(`publish/`)과 대조한 결과(AI~AL)를 합쳤다. 데이터 수집(A/J/K/N)은 이번
조사에서 새로 지적할 만한 gap을 못 찾았다 — 이미 1~3부에서 실측 기반으로
여러 번 보강됐다.

AF는 **실제 프로젝트 데이터로 재현까지 마쳤다** — 나머지는 코드 대조 기반이며,
구현 시 별도로 실측 검증한다(이 세션의 기존 원칙과 동일).

```
AH(슬러그 충돌 경고, 최우선·최저비용) → AF(책 전체 집계 게이팅, 최우선·최고가치)
  → AI(표지·저작권 front matter) → AG(Config 관리) → AK(챕터 간 용어 일관성)
  → AL(찾아보기/색인) → AJ(EPUB 출력)
```

## AF. "최종 선정"이 책 전체가 아니라 임의의 챕터 하나만 판정함 (실측 재현됨)

**문제**: `draft_cmd.py::_draft_one_chapter()`가 챕터마다 새 `PerformanceMonitor`를
만들어 `draft_ch{N}.json`으로 따로 저장한다 — 책 전체를 누적하는 프로젝트 단위
모니터가 없다. `gate_cmd.py::_latest_result_file()`은 `--file`을 안 주면
`eval_results/`에서 **mtime 기준 가장 최근 파일 하나**만 고른다.

실제 프로젝트(`AI_에이전트_평가_입문`, 6챕터)로 지금 재현했다:
```
$ book-forge gate "AI_에이전트_평가_입문" --min-gate-score 0.0
🚦 게이팅 대상: .../eval_results/draft_ch05.json
```
Chapter 5 하나만 게이팅됐다 — 1/2/3/4/6은 완전히 무시됐다. 저자가 자연스럽게
`book-forge gate <slug>`를 실행하면 "책 전체 판정"이 아니라 "가장 최근에
건드린 챕터 하나 판정"이 매번 나온다. `agent-eval gate` CLI는 파일 하나만
받는 구조지만, agent-evaluator에는 이미 `PerformanceMonitor.merge()` +
`load_from_file()`(둘 다 `core/trackers/monitor.py`)가 있어 여러 챕터 결과를
합치는 게 기술적으로 어렵지 않다 — Book-forge 어디서도 이 함수들을 쓰지
않는다(`grep` 결과 0건, 별도 조사로 확인).

**해법**: `gate_cmd.py`에 `--all`(또는 기본 동작 자체를 변경) 옵션을 추가 —
`eval_results/draft_ch*.json`(+ `research_ch*.json` 등 챕터 단위 결과) 전부를
`PerformanceMonitor.load_from_file()`로 불러와 `.merge()`로 하나로 합친 뒤
`.generate_report()` → 임시 병합 JSON을 만들어 기존 `agent-eval gate` 위임
호출에 넘긴다. 새 판정 로직이 아니라 agent-evaluator가 이미 제공하는 병합
기능을 처음으로 실제 사용하는 것 — `book-forge gate`의 코어 위임 방식(항목
"gate_cmd.py 전체 위임")은 그대로 유지한다. `--file`을 명시하면 기존처럼
단일 파일 게이팅도 계속 지원(하위 호환, 특정 챕터만 다시 보고 싶을 때 유용).

**우선순위**: 최우선(파이프라인의 최종 관문이 실질적으로 고장나 있음 — 이
세션에서 나온 어떤 항목보다 사용자 신뢰에 직결).

**상태**: ✅ 완료 (CLAUDE.md 항목 36). 계획과 살짝 다르게 구현: 별도 `--all`
플래그 대신 **기본 동작 자체**를 바꿨다(`--file` 없이 부르면 항상 집계) —
파일이 1개뿐이면 병합 왕복 없이 기존과 동일하게 동작해 하위 호환이 깨지지
않는다. 실측(실제 `AI_에이전트_평가_입문` 프로젝트, 이 문제를 원래 발견한
바로 그 프로젝트): 수정 전엔 `draft_ch05.json` 하나만 게이팅됐는데, 수정
후 `book-forge gate "AI_에이전트_평가_입문" --min-gate-score 0.0`이 7개
파일(챕터 6개 + planning.json)을 자동으로 집계해 `_merged_gate_result.json`
하나로 게이팅했다. 두 번 연속 실행해도 매번 정확히 같은 7개 파일만
입력으로 잡혀(병합 산출물 자체는 다음 집계에서 제외) 피드백 루프가 없음을
확인했다.

## AG. Harness Config가 전부 하드코딩되어 프로젝트별 커스터마이징이 불가능함

**문제**: 모든 에이전트(`planner.py`, `chapter_drafter.py`, `diagram_generator.py`
등)의 `@agent_eval` 데코레이터에 Config가 소스 코드 리터럴로 박혀 있다
(`SLAConfig(p95_ms=60_000, ...)`, `LoopDetectionConfig(consecutive_repeat_threshold=3)`
등). 프로젝트별로 이 값을 바꿀 CLI 옵션도 프로젝트 설정 파일도 없다.

더 구체적으로: `eval/monitor.py::build_book_monitor()`는 `enable_llm_judge`/
`judge_model` 파라미터를 받지만, 7개 CLI 명령(`new`/`draft`/`chat`/`build`/
`research`/`plan`/`review`) 전부를 확인한 결과 **어느 하나도 이 파라미터를
실제로 넘기지 않는다** — 죽은 파라미터다. LLM Judge는 코드를 직접 고치지
않는 한 Book-forge 전체에서 절대 켜지지 않는다. Gate 가중치 조정
(`gate_a_tcr_weight` 등)도 노출조차 안 돼 있다.

**해법**: 전면적인 Config 오버라이드 시스템(33개 Config 전부를 CLI 플래그로
노출)은 과설계다 — 대신 실제로 저자가 조정하고 싶어질 가능성이 높은 항목만
좁게 노출한다:
1. `build_book_monitor(enable_llm_judge=..., judge_model=...)`를 `new`/`draft`에
   `--enable-llm-judge`/`--judge-model` 옵트인 플래그로 연결(파라미터는 이미
   있으니 배선만 하면 됨 — 새 로직 없음).
2. 프로젝트 루트에 선택적 `book_forge_config.toml`(또는 `.env`에 접두어를 둔
   환경변수, 예: `BOOK_FORGE_GATE_A_TCR_WEIGHT`) 하나를 두고,
   `gate_a_tcr_weight`/`gate_c_tcr_weight`/`gate_b_loop_weight`(이미 agent-evaluator가
   지원, CLAUDE.md에 문서화돼 있음) 3개만 우선 노출 — 33개 Config 세부값까지
   가는 건 후속 라운드로 미룬다.

**우선순위**: 중(기능이 "고장"난 게 아니라 "커스터마이징이 안 될 뿐"이라
AF/AH보다 급하지 않음, 그러나 "실제 출판 도구"라면 저자마다 다른 품질
기준을 쓸 수 있어야 한다는 점에서 무시할 수 없음).

**상태**: ✅ 완료 (CLAUDE.md 항목 38). 계획대로 두 갈래 다 구현: (1)
`new`/`draft`에 `--enable-llm-judge`/`--judge-model` 옵트인 플래그를
추가해 `build_book_monitor()`까지 실제로 배선, (2) `BOOK_FORGE_GATE_A_TCR_WEIGHT`/
`BOOK_FORGE_GATE_C_TCR_WEIGHT`/`BOOK_FORGE_GATE_B_LOOP_WEIGHT` `.env` 변수를
`build_book_monitor()`가 읽어 `PerformanceMonitor`에 전달(미지정 시 기존
기본값 그대로, 값이 잘못되면 조용히 무시). `book_forge_config.toml` 대신
`.env`만 썼다 — LLM Provider 선택과 이미 같은 메커니즘이라 새 설정 파일
형식을 하나 더 만들 필요가 없었다. 33개 Config 전체 노출은 계획대로
후속 라운드로 미뤘다(과설계 방지). 실측: LLM Judge는 agent-evaluator가
OpenAI/Anthropic 모델만 지원해(Ollama 무연동 확인) API 키 없이는 실제
채점 호출을 검증할 수 없어 오프라인 스파이 테스트로 배선만 확인했다.
Gate 가중치 오버라이드는 실제 `.env` 파일 → `load_config()`(python-dotenv)
→ `os.environ` → `PerformanceMonitor(gate_a_tcr_weight=0.9)` 전체 경로를
API 키 없이 실측 확인했다(`BOOK_FORGE_GATE_A_TCR_WEIGHT=0.9`를 `.env`에
쓰고 실제로 `_gate_a_tcr_weight == 0.9`로 반영됨을 확인).

## AH. 주제 입력 시 슬러그 충돌을 경고 없이 덮어씀

**문제**: `config.py::ensure_project_dir()`은 `mkdir(parents=True, exist_ok=True)`만
쓴다 — 같은 제목(또는 슬러그가 겹치는 다른 제목)으로 `book-forge new`를 다시
실행하면 기존 `00_기획안.md`/`01_목차.md`가 **경고 없이 덮어써진다**(챕터
파일 자체는 `scaffold.py`가 존재 시 건너뛰지만, 기획안/목차는 무조건 새로
씀).

**해법**: `new_cmd.py`에서 `ensure_project_dir()` 호출 전, `00_기획안.md`가
이미 존재하면 `click.confirm("이미 존재하는 프로젝트입니다. 기획안/목차를
덮어쓰시겠습니까?")`로 확인을 받는다(기본 거부) — 새 판정 로직 없이 존재
여부만 확인하는 가장 저비용 수정.

**우선순위**: 최우선(가장 저비용, 실수로 기존 작업을 날리는 걸 막는 안전
장치 — 이 세션 내내 지켜온 "되돌릴 수 없는 작업 전 확인" 원칙과 직결).

**상태**: ✅ 완료 (CLAUDE.md 항목 35). 구현 중 발견: `get_data_dir()`을
`new_cmd.py`가 직접 import해서 쓰면 테스트의 `monkeypatch.setattr(config_module,
"get_data_dir", ...)`가 반영 안 되는 바인딩 함정이 있어(import 시점 스냅샷),
`config.py`에 `project_dir_for(slug)` 조회 전용 헬퍼를 추가해 우회했다.
실측(실제 Ollama, `/tmp` 격리 환경): 같은 제목으로 두 번째 `new`를 실행하니
"이미 존재하는 프로젝트입니다" 확인 프롬프트가 뜨고, 거부하면 기존 기획안이
그대로 보존됨을 확인했다.

## AI. 표지·저작권·저자 정보 등 출판 전면부(front matter)가 전혀 없음

**문제**: `BookConfig`(`publish/config.py`)는 `title`/`accent_color` 두 필드뿐이다
— 저자명, 저작권/라이선스 고지, 판(edition)/출판일 필드가 없다. `html_builder.py`/
`pdf_builder.py`/`PLAN_PROMPT` 전체를 검색해도 "author"/"저자"/"copyright"/
"저작권"/"ISBN"/"title-page"/"cover" 어느 것도 안 나온다(0건, 직접 확인) —
표지 페이지·저작권 고지 페이지 개념 자체가 파이프라인에 없다. 실제 서점에
낼 수 있는 책이라면 최소한 저자명과 저작권 고지가 있는 표지/판권 페이지가
있어야 한다.

**해법**: `PLAN_PROMPT`에 저자명을 입력받는 필드를 추가하거나(`book-forge new`에
`--author` 옵션, LLM 생성 없이 그대로 저장 — 창작할 대상이 아니므로 LLM 호출
불필요), `BookConfig`에 `author: str = ""`/`license_notice: str = ""`/
`edition: str = "1"` 필드를 추가한다. `html_builder.py`/`pdf_builder.py`가
빌드 시작 부분에 제목+저자+저작권 고지+판을 담은 별도 섹션(`<section
class="title-page">`)을 자동 삽입한다 — 전부 문자열 조립이라 LLM 미호출,
환각 위험 없음.

**우선순위**: 상(V/W/X와 비슷하게 저비용·명확한 스코프, "출판 가능"의 최소
요건에 직접 해당).

**상태**: ✅ 완료 (CLAUDE.md 항목 37). 계획과 살짝 다르게 구현: `PLAN_PROMPT`를
건드리는 대신 완전히 별도인 `front_matter.json` 파일로 분리했다(00_기획안.md의
기존 파싱 계약을 안 깨기 위해 — `plan_cmd.py::_strip_title_h1()`이 정확히
`"# {title}\n\n"` 형식을 가정하고 있어서 그 사이에 저자명 줄을 끼워 넣으면
깨졌을 것). `edition` 기본값도 `"1"`이 아니라 `""`로 바꿨다(전부 빈 값이면
표지 자체를 안 만드는 `is_empty` 판정과 자연스럽게 맞물리도록). PDF는
챕터별 개별 파일 구조라 표지도 `00_표지.pdf`라는 별도 파일로 만든다.
실측(실제 Ollama + 실제 Playwright, `/tmp` 격리 환경): `--author 김성우
--license-notice "..." --edition "1판 1쇄"`로 프로젝트를 만들고
`book-forge build html`/`build pdf`를 둘 다 돌려, HTML에는
`<section class="title-page">`가 올바른 값으로 렌더링됐고 PDF에는
`00_표지.pdf`(46KB, 실제 내용 있음)가 챕터 PDF들보다 먼저 생성됨을
확인했다.

## AJ. EPUB 등 전자책 배포 포맷 미지원

**문제**: Book-forge는 HTML/PDF/Slides만 만든다(`publish/` 디렉토리 확인). 실제
전자책 유통(Amazon KDP, 교보문고 e-book 등)은 대부분 EPUB을 요구한다 —
HTML/PDF만으로는 이런 채널에 낼 수 없다.

**해법**: 이미 있는 `md_to_html()`(챕터별 HTML 조각) + `01_목차.md` 매니페스트를
재사용해 EPUB 컨테이너(챕터별 XHTML + `content.opf` 메타데이터 + `nav.xhtml`
목차)를 조립하는 `epub_builder.py`를 신설한다. 순수 zip 아카이브 포맷이라
Playwright 같은 무거운 브라우저 의존성이 필요 없다(PDF 빌드와 다른 지점) —
표준 라이브러리 `zipfile`만으로 가능. 이미지도 base64 인라인 대신 EPUB 컨테이너
안에 실제 파일로 포함해야 한다는 점이 HTML 빌드와 다르다.

**우선순위**: 하(새 산출물 포맷 하나를 통째로 추가하는 작업이라 상대적으로
크고, "웹/PDF로 우선 배포"가 이미 되는 상태에서 급하지 않음 — 저자가 실제
전자책 채널 유통을 계획할 때 재검토).

**상태**: ✅ 완료 (CLAUDE.md 항목 41). 계획대로 `epub_builder.py`를 새로
만들어 `zipfile` 표준 라이브러리만으로 EPUB 3 컨테이너(mimetype +
META-INF/container.xml + OEBPS/content.opf + nav.xhtml + 챕터별 XHTML)를
조립한다 — Playwright 의존성 없음. `md_to_html()`은 그대로 재사용하고,
이미지는 SPEC이 명시한 대로 base64 인라인 대신 실제 파일로 컨테이너에
포함한다(`markdown_engine.rewrite_images_for_epub()` 신설 — `embed_images_as_data_uri()`의
EPUB 전용 짝). `book-forge build epub <slug>` 명령 추가. 계획에는 없던
안전장치를 하나 추가했다: mermaid/커스텀 HTML 원문 블록은 HTML/PDF와
동일하게 escape 없이 삽입되는데, EPUB 리더는 XML 파서가 훨씬 엄격해
짝이 안 맞는 태그 하나가 파일 전체를 못 열게 만들 수 있다 — 챕터별 XHTML을
`xml.etree.ElementTree`로 well-formed 여부를 확인해, 실패하면 그 챕터만
escape된 원문 텍스트로 안전하게 대체한다(다른 챕터는 영향 없음). 알려진
한계로 명시: EPUB 리더 대부분은 리플로우 컨텐츠에서 JS를 실행하지 않아
mermaid 다이어그램은 렌더링되지 않고 원본 텍스트로 보인다(PDF의 Mermaid
잘림과 같은 급의 한계). 실측(실제 `AI_에이전트_평가_입문` 프로젝트, 6챕터):
48KB EPUB이 생성됐고, `zipfile.testzip()`로 무결성 확인 + mimetype이
비압축 첫 항목임을 확인 + `content.opf`/`nav.xhtml`/챕터 6개 XHTML 전부
`ET.fromstring()`으로 well-formed XML 파싱 성공을 확인했다(epubcheck는
환경에 없어 못 돌렸지만, zip 무결성 + 전체 XML well-formedness는 EPUB이
"열리기라도 하는지"의 핵심 조건이라 충분한 신호로 판단).

## AK. 챕터 간 용어·스타일 일관성을 검사하지 않음

**문제**: 각 챕터는 독립된 LLM 호출 + 독립된 RAG 검색 컨텍스트로 생성된다 —
같은 개념을 챕터마다 다르게 부를 위험이 구조적으로 있다. 이 세션에서 이미
**실제로 관찰**했다: `--all` 배치 재생성 중 Chapter 3과 Chapter 5가 서로 다른
주제였는데도 둘 다 `conversation.py`의 한국어 토큰나이저 내용으로 드리프트된
사례(같은 소스가 여러 챕터에서 서로 다른 맥락으로 재사용된 것 — 정확히 이
항목이 우려하는 "챕터 간 일관성 없는 재사용"의 실제 사례). `grep`으로
확인한 결과 "용어 사전"은 TOC 프롬프트의 예시 문구로만 존재할 뿐, 실제
용어 일관성을 검사하는 코드는 어디에도 없다.

**해법(범위를 의도적으로 좁힘)**: 전체 도서를 대상으로 한 정교한 NLP 기반
용어 정합성 검사는 과설계 위험이 크다 — 대신 이미 있는 인프라를 재사용하는
가장 저비용 버전부터: `book-forge gate`(AF로 책 전체 집계가 가능해진 뒤)와
별개로, `book-forge lint`(가칭) 같은 옵트인 명령이 전체 챕터의 백틱 기술
용어(코드-본문 정합성 검사기의 `_looks_like_class_name()`과 같은 휴리스틱
재사용 가능)를 모아, 같은 개념으로 보이는 서로 다른 표기(예: "Gate" vs
"게이트")가 여러 챕터에 흩어져 있으면 목록으로 보고한다 — LLM이 직접
"통일"하지 않고 저자에게 후보만 보여준다(module_reference의 "코드가 목록을
결정, LLM은 설명만" 원칙과 유사).

**우선순위**: 중(실측으로 확인된 실제 문제지만, 자동 수정까지는 위험해
"발견해서 보고"까지만 하는 저비용 버전으로 시작).

**상태**: ✅ 완료 (CLAUDE.md 항목 39). 계획대로 새 `book-forge lint <slug>`
명령을 추가했다 — `code_consistency_checker._BACKTICK_RE`/
`_BUILTIN_EXCLUSIONS`를 재사용해 전체 챕터의 백틱 기술 용어를 뽑고,
대소문자·구두점을 제거한 "접힌 키"가 같은데 실제 표기가 다른 경우만
후보로 보고한다(`ToolCallAnalyzer` vs `tool_call_analyzer` 같은 구조적
변형만 — "Gate" vs "게이트" 같은 한영 동의어 탐지는 SPEC이 명시한 대로
과설계 위험 때문에 범위에서 제외). 자동 수정 없음, 발견·보고만
(`--fail-on-inconsistency`로 CI 연동만 옵트인). 실측(실제 `AI_에이전트_평가_입문`
프로젝트, 6개 챕터): `generate_report`/`_generate_report`,
`Settings`/`_settings` 두 건의 실제 표기 불일치를 찾아냈다 — 읽기 전용이라
프로젝트 콘텐츠에 부작용 없음.

## AL. 찾아보기(색인)가 없음

**문제**: 실제 기술 서적은 대부분 책 끝에 키워드 → 페이지/섹션 찾아보기가
있다. Book-forge에는 이 개념이 전혀 없다(`grep`으로 "찾아보기"/"색인"/
"index" 검색 결과 소스 어디에도 없음).

**해법**: PDF 빌드는 최종 산출물이 페이지 번호를 갖는 유일한 포맷이므로,
`pdf_builder.py`가 각 챕터의 백틱 기술 용어(코드 일관성 검사기가 이미
추출하는 것과 같은 패턴)를 수집해 챕터 제목→(가능하면 페이지 번호) 매핑을
만들고, 책 끝에 "찾아보기" 섹션을 자동 생성하는 옵트인 단계를 추가한다.
HTML은 페이지 개념이 없으므로 챕터 링크로 대체.

**우선순위**: 중하(AK와 관련 있지만 별개 — AK가 "일관성 발견"이라면 AL은
"이미 일관된 용어의 내비게이션 보조". AK가 먼저 다뤄질수록 AL의 결과물
품질도 좋아짐 — AK 이후 순서 권장).

**상태**: ✅ 완료 (CLAUDE.md 항목 40). AK 직후 구현해 계획대로 그 백틱
추출 로직(`term_consistency_checker._extract_terms`)을 그대로 재사용했다
— 새 `publish/book_index.py::build_index_entries()`가 용어→등장 챕터
매핑을 만들고, `html_builder.py::build_index_section()`/
`pdf_builder.py`가 각각 렌더링한다. `book-forge build html/pdf`에
`--with-index` 옵트인 플래그를 추가(기본 off — SPEC이 명시한 "옵트인
단계"). HTML은 SPEC이 명시한 대로 실제 챕터 앵커 링크(단일 파일이라
가능), PDF는 챕터별 개별 파일 구조라 파일을 가로지르는 실제 페이지
번호가 존재할 수 없어 챕터 번호/제목 텍스트로 정직하게 절충했다(AI의
표지와 같은 패턴으로 `99_찾아보기.pdf` 별도 파일). 실측(실제
`AI_에이전트_평가_입문` 프로젝트): HTML은 `__repr__`/`_chunk_text` 등
실제 코드 식별자로 색인이 채워지고 앵커 링크(`href="#ch03"` 등)가 실제
챕터 섹션을 정확히 가리켰다. PDF는 78KB `99_찾아보기.pdf`가 7번째
파일로 정상 생성됨을 확인했다.

---

## 구현 순서 및 상태 (4부)

| 항목 | 상태 |
|---|---|
| AH | ✅ 완료 (CLAUDE.md 항목 35 — 슬러그 충돌 경고) |
| AF | ✅ 완료 (CLAUDE.md 항목 36 — 책 전체 집계 게이팅) |
| AI | ✅ 완료 (CLAUDE.md 항목 37 — 표지·저작권 front matter) |
| AG | ✅ 완료 (CLAUDE.md 항목 38 — Config 관리: LLM Judge 배선 + Gate 가중치 3종 `.env` 노출) |
| AK | ✅ 완료 (CLAUDE.md 항목 39 — `book-forge lint`: 챕터 간 용어 표기 불일치 발견·보고) |
| AL | ✅ 완료 (CLAUDE.md 항목 40 — `--with-index`: 찾아보기/색인 자동 생성) |
| AJ | ✅ 완료 (CLAUDE.md 항목 41 — `book-forge build epub`: EPUB 3 출력) |
