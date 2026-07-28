# Chapter 8. 에이전트별 품질 계약 — 무엇을 보장하고, 무엇이 문제이며, 어떻게 재는가

> ## Part III. 배치 평가로 품질을 계측한다
> Part II가 "에이전트들이 어떻게 협업하는가"를 다뤘다면, Part III의 6개 챕터는 그 협업이 만든 **결과물의 품질을 어떻게 판정하는가**로 초점을 옮긴다. 이 챕터(8장)는 Book-forge 파이프라인이 실행되는 순서 그대로, 에이전트 16개(LLM 14개 + 실시간 가드레일 2개) 하나하나가 "무엇을 보장해야 하고, 무엇이 문제가 될 수 있고, agent-evaluator가 그걸 어떻게 재고 처리하는가"를 표로 정리한다. 9장은 같은 재료를 이번엔 **Gate A–G 축**으로 다시 재편성한다. 이어서 그 매핑과 가중치를 설계하는 방법론(10장), Gate가 손대지 않는 영역인 정적 검증(11장), 챕터 하나가 아니라 책 전체를 판정하는 집계(12장), 마지막으로 이 모든 것을 CI/CD로 자동화하는 방법(13장)까지 다룬다.

> **이 챕터에서 배우는 것**
> - Book-forge 파이프라인이 실행되는 순서대로, 16개 컴포넌트 각각이 무엇을 하고 무엇을 보장해야 하는지
> - 3장이 분류한 실패 유형이 각 컴포넌트에서 구체적으로 어떤 모습으로 나타나는지
> - agent-evaluator가 그 위험을 어떤 Tracker·Config로 측정하고, 배치(Gate 점수)와 실시간(즉시 차단) 중 어느 쪽으로 처리하는지

> **이런 분이 먼저 읽으면 좋습니다**: Part II에서 각 에이전트가 "무엇을 하는지"는 봤지만, "그래서 이 에이전트가 무엇을 보장해야 하고 agent-evaluator가 정확히 그걸 어떻게 재는지"가 아직 하나로 이어지지 않는 분.

---

## 8.1 이 표를 읽는 법

이 챕터의 표는 다섯 열로 이뤄진다.

| 열 | 의미 |
|---|---|
| **무엇을 하는가** | 이 컴포넌트의 역할 한 줄 — 자세한 동작은 Part II(해당 챕터)를 참고 |
| **보장해야 할 품질** | 이 컴포넌트가 실패하지 않으려면 지켜야 할 것 |
| **예상·실제 문제** | 그 품질이 깨지면 벌어지는 일 — 3장이 분류한 5가지 실패 유형(무응답·환각·드리프트·반복·경로 침범) 중 무엇에 해당하는지 태그로 표시 |
| **측정** | agent-evaluator의 어느 Tracker·Config가 이 위험을 계측하는가 |
| **처리** | **배치**(`book-forge gate` 실행 시 Gate A–G 점수에 반영, 사후 채점) 또는 **실시간**(`@tool_guard`, 실행 **전**에 차단) — 이 둘은 완전히 다른 축이다(14장) |

파이프라인 실행 순서(`new` → `research`/`draft` → `chat` → `review` → `build slides`, 그리고 언제든 병행 가능한 `edit`)를 그대로 따라간다.

## 8.2 기획·목차·스캐폴딩 — 승인 루프를 거쳐 첫 파일이 만들어지기까지

| 컴포넌트 | 무엇을 하는가 | 보장해야 할 품질 | 예상·실제 문제 | 측정 | 처리 |
|---|---|---|---|---|---|
| **PlannerAgent**(2장) | 주제·제약 → 기획안 마크다운 생성 | 주제/제약을 실제로 반영 · `## 목적` 등 마크다운 구조 준수(다음 단계 파싱 계약) · 최소한의 근거 포함 | 지시사항 무시(헤딩 누락 → 이후 파싱 실패로 전이) · 근거 없는 두루뭉술한 텍스트 | `GoalAlignmentConfig`(Gate A) · `InstructionConfig`(위반 기록, 즉시실패 아님) · `ExplainabilityConfig`(Gate G, 최소 30자 근거) | 배치 — Gate A/G |
| **`revise()`**(AuthorReviewLoop, 6장) | 저자 피드백을 반영해 기획안/목차를 재생성(기획·목차 두 곳에서 동일 함수 재사용) | 저자가 요청한 것을 실제로 반영 · 같은 피드백에 무한정 반복하지 않아야 | **반복**(3.4) — 저자가 같은 피드백을 실수로 반복 입력, 무한 루프 위험 | `LoopDetectionConfig(consecutive_repeat_threshold=3)`(Gate B, `task_id_fn`으로 라운드별 개별 기록) + `MAX_REVIEW_ROUNDS=5`(애플리케이션 레벨, SDK 기능 아님) | 배치(Gate B) + 애플리케이션 이중 방어 |
| **TOCDesignerAgent**(4장) | 기획안(+선택적 `code_structure`) → 목차 마크다운(사람이 읽는 부분 + ` ```toc ` 매니페스트) | 기획안의 결정사항(대상 독자·차별점 등)을 커버 · 챕터들이 하위 작업(subtask)으로서 커버리지 충족 · ` ```toc ` 블록 형식 정확히 준수(파싱 계약) | **환각**(3.2) — 실제로 존재하지 않는 서브시스템을 목차에 지어낼 위험(`code_structure` 주입으로 완화) · 형식 위반 시 `TocParseError` | `PlanConfig` + `SubtaskConfig` + `ContextRetentionConfig`(전부 Gate A) | 배치 — Gate A (파싱 실패는 Gate 점수가 아니라 예외로 즉시 드러남) |
| **ScaffoldAgent**(`write_chapter_stub`, 3·14장) | 목차 매니페스트 → 실제 챕터 스텁 파일 생성 | 프로젝트 디렉토리 밖에 쓰지 않아야 · 같은 호출을 무한 반복하지 않아야 | **경로 침범**(3.5) · **반복**(3.4) | `LoopDetectionConfig(consecutive_repeat_threshold=5)`(LiveGuardrail) — 경로 검사는 SDK가 아니라 `resolved_project not in resolved_target.parents`로 직접 구현 | **실시간** — `@tool_guard` + `live_guardrail_session`, 쓰기 실행 **전**에 차단, Gate 점수와 무관 |

## 8.3 콘텐츠 생성 — 일곱 생성기

`--source`가 있으면 스캐폴딩 직후 곧바로, 아니면 저자가 `book-forge draft`를 실행할 때 이 단계가 시작된다.

| 컴포넌트 | 무엇을 하는가 | 보장해야 할 품질 | 예상·실제 문제 | 측정 | 처리 |
|---|---|---|---|---|---|
| **ResearchAgent** | 챕터 제목 → 검색 쿼리 생성(실제 웹 검색·선택은 저자가 별도로 수행) | 챕터 제목의 맥락을 반영한 쿼리를 만들어야 | 저위험군 — 외부 콘텐츠를 직접 프롬프트에 섞지 않으므로 인젝션 위협이 없다(`sources` 인자 자체가 없음) | `InstructionConfig`만 | 배치 — Gate A 정도, 나머지는 대체로 N/A |
| **AlternativeSuggesterAgent** | 소스 커버리지가 낮거나 실증이 어려울 때 저자에게 대안 제시 — 단순 경고로 끝내지 않고 다음 행동을 고르게 함 | `chapter_title`/`reason`을 실제로 반영 · 최소한의 근거(10자) 포함 | `draft_cmd.py`의 RAG 커버리지 체크(평균 코사인 유사도가 `--min-coverage` 미만)가 이미 위험 신호를 낸 **뒤에** 호출됨 — 이 신호는 Agent-Evaluator Gate 점수가 아니라 검색 자체의 품질 휴리스틱이다 · 소비 못 하면 저자가 위험을 인지 못한 채 진행될 수 있음 | `InstructionConfig` + `ExplainabilityConfig(min_reasoning_length=10)` | 배치 — Gate A/G |
| **ChapterDrafterAgent**(narrative·exercise) | RAG 소스 + 챕터 제목 → 챕터 본문 생성 | 소스에 근거해야(환각 금지) · SLA(60초/90초) 내 응답 · 외부 RAG 콘텐츠의 프롬프트 인젝션에 안전 | **환각**(3.2) — 존재하지 않는 API 인용 · SLA 초과(9장 §9.5 실측: 로컬 35B 모델에서 D=0.135) · RAG 소스 오염 | `HallucinationDetector`(rag_mode 자동, Gate C) · `SLAConfig`(Gate D) · `ThreatSeverityConfig`(Gate E) | 배치 — Gate C/D/E + 생성 직후 정적 검증(11장, Gate 미반영·참고용) |
| **ReferenceTableAgent** | RAG 소스 → 구조화된 사실(용어·API·명령어·파라미터)을 마크다운 표로 | 소스에 명시된 값만("확인되는 값만" 원칙) — 확인 안 되면 행 자체를 생략 | 검색이 놓친 항목은 조용히 **누락**됨(실측: Book-forge 자신의 `agents/` 13개 파일 중 4개만 우연히 top-k에 뽑혀 다뤄짐) · RAG 오염 | ChapterDrafterAgent와 동일 3종(Gate C/D/E) | 배치 + 정적 검증(표 셀이 실제 소스에 등장하는가) |
| **DiagramGeneratorAgent** | RAG 소스 → mermaid 다이어그램 | 알려진 mermaid 타입으로 시작 · 노드/엣지가 실제 구조에 근거 | 100% LLM이 그래프 구조 자체를 새로 구성하므로 서술형보다 **환각** 위험이 큼(실측: "패키지 구조"를 요청했는데 파일 하나의 내부 관계만 그려진 스코프 불일치) | 동일 3종(Gate C/D/E) | 배치 + 정적 검증(`verify_diagram`, `min_grounding_ratio=0.3`) |
| **CapstoneGeneratorAgent** | 빈 실습 템플릿 + 별도 정답을 **한 번의 호출**로 구분자(`=== TEMPLATE ===`/`=== SOLUTION ===`)로 생성 | 템플릿엔 정답을 채우지 않아야 · 정답은 TODO 없이 완전해야 · 템플릿과 정답이 같은 문제를 다뤄야 | 두 번 호출하면 템플릿·정답이 서로 다른 문제를 다룰 위험(예: 템플릿은 리스트 실습인데 정답은 딕셔너리 실습) — 그래서 반드시 한 번의 호출·같은 컨텍스트에서 나오게 설계됨 | 동일 3종(SLA만 90/120초로 더 여유) + `parse_capstone_response()`의 관대한 파싱(구분자 없으면 예외 대신 템플릿=원문, 정답=빈 문자열로 폴백) | 배치 + 정적 검증(TODO 마커 대조) |
| **ModuleReferenceAgent** | 구조적 코드 인덱싱(4장, `code_index.py`)이 만든 **전체** 모듈/클래스/함수 목록 → 레퍼런스 문서(RAG 검색이 아니라 결정론적 전체 목록을 그대로 받음) | "빠짐없이" 원칙 — 실제 존재하는 모든 항목을 다뤄야 | ReferenceTableAgent와 **정반대** 실패 모드 — "확인되는 값만"(누락 가능) 대신 "빠짐없이"(날조 가능): 있지도 않은 항목을 있는 것처럼 만들 위험 | `rag_mode=True`이지만 `sources`가 검색 결과가 아니라 전체 구조 요약(최대 8000자, 다른 생성기의 6000자보다 여유) — `HallucinationDetector`(Gate C, 다른 방식으로 근거 대조) + `SLAConfig(90s/120s)`·`ThreatSeverityConfig`(Gate D/E, Capstone과 동일하게 여유 있는 SLA) | 배치 + 정적 검증(`verify_module_reference_coverage()`) |

RAG 생성기 5개는 표 형태로는 다르게 보이지만, 계측 배선은 거의 동일한 틀을 복사한다. 가장 먼저 만들어진 `ChapterDrafterAgent`가 그 원형이다.

> 📄 **파일**: `src/book_forge/agents/chapter_drafter.py`

```python
def build_draft_chapter(llm: LLM, monitor: PerformanceMonitor) -> DraftFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="chapter_title",
        rag_mode=True,
        context_arg="sources",
        # Gate D: 소스가 길면 응답이 오래 걸릴 수 있어 여유 있게 설정.
        sla=SLAConfig(p95_ms=60_000, p99_ms=90_000),
        # Gate E: 외부 PDF/문서(RAG 소스)에 프롬프트 인젝션이 섞여 있을 가능성.
        threat_severity=ThreatSeverityConfig(),
    )
    def draft_chapter(
        chapter_title: str, chapter_no: int, sources: str,
        ground_truth: str = "", content_type: str = "narrative",
    ) -> tuple[str, EvalMetadata]:
        template = _CONTENT_TYPE_PROMPTS.get(content_type, DRAFT_PROMPT)
        prompt = template.format(
            chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000]
        )
        draft_md = llm.generate(prompt, system=DRAFT_SYSTEM_PROMPT, max_tokens=3000)
        return draft_md, EvalMetadata(extra={"phase": "drafting", "chapter_no": chapter_no})

    return draft_chapter
```

데코레이터 인자 옆 주석이 §8.3 표의 "측정" 열이 어디서 나왔는지 그대로 보여준다. `sla=`는 Gate D를, `threat_severity=`는 Gate E를 겨냥한다는 것을 코드를 쓴 사람이 직접 남겨둔 것이다. `content_type` 인자는 `_CONTENT_TYPE_PROMPTS`에 있는 `"exercise"` 하나만 다른 프롬프트로 갈아끼우고, 나머지는 전부 `DRAFT_PROMPT`(narrative 기본값)로 떨어진다 — `reference_table`/`diagram`/`capstone`/`module_reference` 네 유형은 이 함수까지 오지 않고 `draft_cmd.py`가 애초에 다른 에이전트로 통째로 라우팅한다. §8.3의 나머지 4개 RAG 생성기(ReferenceTable·Diagram·ModuleReference·아래 Capstone)는 이 뼈대에서 프롬프트와 SLA만 바꿔 낀 변형이다.

> 📄 **파일**: `src/book_forge/agents/capstone_generator.py` (`parse_capstone_response()`)
>
> ```python
> def parse_capstone_response(raw: str) -> tuple[str, str]:
>     t_match = _TEMPLATE_MARKER_RE.search(raw)
>     s_match = _SOLUTION_MARKER_RE.search(raw)
>     if not t_match or not s_match or s_match.start() <= t_match.start():
>         return raw.strip(), ""   # 구분자가 없거나 순서가 뒤바뀌면 예외 없이 폴백
>     template = raw[t_match.end():s_match.start()].strip()
>     solution = raw[s_match.end():].strip()
>     return template, solution
> ```
>
> 정답이 빈 문자열로 돌아오면, 호출부가 이걸 "검증 실패"로 처리한다. **형식 위반을 예외로 죽이지 않고, 빈 정답이라는 관찰 가능한 신호로 바꿔 다음 단계(정적 검증)가 판단하게 넘긴다.**

## 8.4 대화·검토 — 산출물이 파일이 아닌 세 에이전트

| 컴포넌트 | 무엇을 하는가 | 보장해야 할 품질 | 예상·실제 문제 | 측정 | 처리 |
|---|---|---|---|---|---|
| **ChatAgent**(7장) | 지식창고 발췌문 + 질문(+대화 이력) → 답변(REPL 즉시 출력) | 지식창고에 근거 · SLA 30초(대화형이라 Drafter의 60초보다 짧음) · 프롬프트 인젝션에 안전 | **환각** — ChapterDrafterAgent와 동일한 위협(산출물이 파일이 아니라는 점은 위협 자체와 무관, 실측: 이 Config가 한때 누락돼 있었음) | `HallucinationDetector`(Gate C) · `SLAConfig(30s)`(Gate D) · `ThreatSeverityConfig`(Gate E) | 배치(질문 단위) + `ConversationSession`(세션 전체 흐름 지표, **Gate 미반영·완전히 별도 축**) |
| **ReviewerAgent** × N(5장) | 같은 챕터를 서로 다른 관점(정확성·가독성)에서 독립적으로 검토 | 자기 관점을 벗어나지 않아야(정확성 담당이 문체를 지적하면 역할 이탈) | 역할 이탈 — 다른 리뷰어의 영역을 침범 | `AgentRoleConfig(allowed/forbidden_action_keywords, role_violation_penalty=0.3)` + `track_interaction()`(`AgentCoordinationTracker`) | 배치 — **Gate F**(Book-forge에서 유일하게 실측 값이 나오는 지점) |
| **ChiefEditorAgent**(5장) | 리뷰어들의 판정을 종합해 최종 결론 | 리뷰어 간 불일치를 실제로 언급하고 조정해야 | 불일치를 무시한 채 근거 없이 결론을 낼 위험 | `ConflictResolutionConfig` — `eval_consensus()`로 계산된 합의도(`consensus_score`)를 프롬프트 조립 **이전**에 미리 받음 | 배치 — Gate F |

## 8.5 부가·실시간 — 파이프라인 밖에서 언제든 개입하는 둘

| 컴포넌트 | 무엇을 하는가 | 보장해야 할 품질 | 예상·실제 문제 | 측정 | 처리 |
|---|---|---|---|---|---|
| **SlideCondenserAgent** | 책 섹션 하나 → 슬라이드 한 장(`TITLE:`/`BULLET:`/`NOTES:` 접두어 형식) | 제목 35자 이내 · 섹션 제목/핵심어 반영 · 챕터당 여러 번 호출되므로 응답이 과도하게 느려지면 안 됨 | 로컬 소형 모델이 유효한 JSON을 안정적으로 못 지키는 경우가 많음 — 형식을 어겨도 파싱이 완전히 죽지 않고 폴백(정답 없으면 본문 첫 줄을 bullet로 대체) | `InstructionConfig` + `ExplainabilityConfig`(Gate A/G) + `SLAConfig(20s/30s)`(Gate D) | 배치 — Gate A/D/G |
| **에디터 저장**(`_write_chapter_file`, 15장) | 웹 에디터에서 챕터 저장 | 다른 저자가 이미 선점(claim)한 스코프를 침범하지 않아야 | 동시 편집 충돌 — 두 저자가 같은 Part를 동시에 저장 | `TeamConcurrencyConfig`(`.aoo/claims.jsonl` 재사용) | **실시간** — `GuardrailBlockedError` → HTTP 409, Gate와 무관. 서버 강제가 아니라 클라이언트 자발적 클레임에 의존(한계, 17장) |

> 📄 **파일**: `src/book_forge/agents/alternative_suggester.py`
>
> ```python
> @agent_eval(
>     monitor, task_type="planning", question_arg="reason",
>     instructions=InstructionConfig(fail_on_violation=False),
>     explainability=ExplainabilityConfig(min_reasoning_length=10),
> )
> def suggest_alternatives(chapter_title: str, reason: str, ground_truth: str = "") -> tuple[str, EvalMetadata]:
>     prompt = ALT_SUGGEST_PROMPT.format(chapter_title=chapter_title, reason=reason)
>     raw = llm.generate(prompt, system=ALT_SUGGEST_SYSTEM_PROMPT, max_tokens=800)
>     return raw, EvalMetadata(extra={"phase": "alternative_suggestion", "reason": reason})
> ```
>
> 이 에이전트가 §8.3 표에서 유독 특별한 이유는 시그니처에 있다. `reason` 인자에는 `draft_cmd.py`가 이미 계산해둔 값이 그대로 들어간다. 실제 호출부(`draft_cmd.py`)를 보면 이렇다.
>
> ```python
> reason=f"평균 소스 유사도 {avg_score:.3f}로 낮음 (top_k={top_k}개 청크 검색)",
> ```
>
> `avg_score`는 `KnowledgeStore.query_with_scores()`가 돌려준 코사인 유사도 평균이고, 이 값이 `--min-coverage` 임계값에 못 미쳤다는 사실 자체가 `reason` 문자열이 된다. **이 판단은 Agent-Evaluator의 Gate 점수가 아니다** — `book-forge gate`가 아직 실행되지 않은, 생성 직전 시점이라 Gate A–G 점수 자체가 아직 존재하지 않는다. (`alternative_suggester.py`의 모듈 docstring은 이 트리거를 "C(근거 검증 계층)·D(실증 가능성 게이트)"라 부르는데, 이는 `SPEC.md`가 매긴 Book-forge **자체** 기능 번호(`일반 능력 A~Z`)이지 Agent-Evaluator의 Gate C·D와는 무관하다 — 알파벳이 겹치는 우연일 뿐이며, 헷갈리기 쉬운 지점이다.) 즉 이 에이전트는 새로운 위험을 만드는 게 아니라, **이미 `draft_cmd.py` 자신이 계산한 검색 품질 경고를 소비해서** 저자가 다음 행동을 고를 수 있는 구체적 선택지로 바꾸는 안전판이다.

## 8.6 Config를 고르는 법 — 이 표를 거꾸로 읽는다

16개 컴포넌트를 나란히 놓고 보면 Config 선택이 무작위가 아니라 두 가지 질문에서 곧바로 도출된다는 것이 보인다.

**① 이 함수가 부작용을 일으키는가?** — 부작용이 있는 함수(파일 쓰기)는 애초에 `@agent_eval`이 아니라 `@tool_guard`를 쓴다(§8.2의 ScaffoldAgent, §8.5의 에디터 저장). "결과를 만드는 함수"는 사후 채점하고, "부작용을 일으키는 함수"는 실행 전에 막는다 — 이 구분이 이 책의 핵심 축이다.

**② 신뢰 못 할 외부 콘텐츠를 다루는가?** — `rag_mode=True`인 6개 에이전트(ChapterDrafter·ReferenceTable·Diagram·Capstone·ModuleReference·Chat) **전부**가 `ThreatSeverityConfig`도 함께 쓴다. 외부에서 온 RAG 소스를 프롬프트에 직접 섞기 때문이다. 반대로 ResearchAgent는 `sources` 인자 자체가 없어(검색 **쿼리**만 만들 뿐, 검색된 콘텐츠는 저자가 검토한 뒤에야 지식창고에 들어간다) 이 Config가 필요 없다. `rag_mode=True`인가로 `threat_severity` 필요 여부를 100% 예측할 수 있다(실측 반례: 이전 버전 `chat_agent.py`는 `rag_mode=True`이면서도 이 Config가 누락돼 있었다 — §8.4 실측 사례).

```mermaid
flowchart TD
    Q1{"이 함수가<br/>부작용을 일으키는가?"}
    Q1 -->|"예(파일 쓰기 등)"| TG["@tool_guard + live_guardrail_session<br/>(14장)"]
    Q1 -->|"아니오(응답만 반환)"| Q2{"신뢰 못 할 외부<br/>콘텐츠를 다루는가?"}
    Q2 -->|"예"| TS["threat_severity=ThreatSeverityConfig()"]
    Q2 -->|"아니오"| Q3{"이전 단계의<br/>의도를 지켜야 하는가?"}
    Q3 -->|"예"| GA["goal_alignment / plan_tracking 등"]
    Q3 -->|"아니오"| Q4{"여러 에이전트가<br/>같은 대상을 다루는가?"}
    Q4 -->|"예"| AR["agent_role / conflict_resolution(5장)"]
    Q4 -->|"아니오"| SLA["최소한 sla=SLAConfig()는 고려"]
```

> 📋 **QA 관리자 TIP**: 16개 컴포넌트 중 어느 하나도 33개 Harness Config를 전부 쓰지 않는다. ReviewerAgent·ChiefEditorAgent·`revise()`·ResearchAgent 넷은 각 1개만, RAG 생성기 5개(ChapterDrafter·ReferenceTable·Diagram·Capstone·ModuleReference)와 ChatAgent·AlternativeSuggester는 2개, PlannerAgent·TOCDesignerAgent·SlideCondenserAgent는 3개를 쓴다. "Config를 많이 켤수록 안전하다"는 것은 이 코드베이스가 보여주는 실제 관례가 아니다. 오히려 "이 에이전트가 정말로 무엇을 할 수 있는가"를 좁게 규정한 뒤, 그 범위에 정확히 맞는 Config만 켜는 것이 Book-forge의 일관된 패턴이다.

---

## 직접 해보기

§8.6의 결정 트리를 여러분의 에이전트(또는 3장 "직접 해보기"에서 점검한 에이전트)에 실제로 적용해보라. 답이 전부 "아니오"라면 `SLAConfig` 하나만으로 충분할 수도 있다. 한 걸음 더 나아가려면, §8.2~8.5의 표 형식(무엇을 하는가 / 보장해야 할 품질 / 예상·실제 문제 / 측정 / 처리)을 그대로 빈 칸으로 복사해 여러분의 에이전트 하나에 채워보라. 다섯 칸 중 하나라도 "모르겠다"가 나온다면, 그게 바로 이 에이전트를 프로덕션에 내보내기 전에 먼저 답해야 할 질문이다.

## 이 챕터의 핵심

- **품질 계약은 다섯 조각으로 완결된다.** 무엇을 하는가 → 무엇을 보장해야 하는가 → 무엇이 문제가 되는가(3장의 실패 유형과 연결) → 무엇으로 재는가 → 배치인가 실시간인가.
- **Config 선택은 두 질문에서 도출된다.** 부작용 유무(배치 vs 실시간의 경계), 신뢰 경계(외부 RAG 콘텐츠 여부)가 그것이다.
- **같은 실패 유형이 컴포넌트마다 다른 모습으로 나타난다.** "환각"은 ChapterDrafter에서는 존재하지 않는 API 인용, ReferenceTable에서는 조용한 누락, ModuleReference에서는 정반대인 날조로 나타난다.
- **적게, 정확하게 쓰는 것이 Book-forge의 관례다.** 모든 Config를 켜는 것이 아니라, 이 에이전트에 실제로 필요한 것만 켠다.

## 참고 자료

- 3장 — 5가지 실패 유형 분류 체계(이 표의 "예상·실제 문제" 열이 참조하는 원본)
- `src/book_forge/agents/planner.py`·`toc_designer.py`·`review_loop.py`·`scaffold.py` — §8.2
- `src/book_forge/agents/research_agent.py`·`alternative_suggester.py`·`chapter_drafter.py`·`reference_table.py`·`diagram_generator.py`·`capstone_generator.py`·`module_reference.py` — §8.3
- `src/book_forge/agents/chat_agent.py`·`review_panel.py` — §8.4
- `src/book_forge/agents/slide_condenser.py`·`editor/server.py` — §8.5

---

> **다음 챕터**는 이 표를 Gate A–G 축으로 다시 편성한다 — 같은 16개 컴포넌트가 7개 Gate 중 정확히 어디에 값을 채우는지, 그리고 왜 어떤 Gate는 자주 N/A로 나오는지를 다룬다.
