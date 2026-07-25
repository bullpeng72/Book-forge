# 부록 A. Harness Config 사용 현황

이 책 15개 챕터가 인용한 Harness Config·트래커·검증기 전체를 에이전트별로 재정렬한 참조표다. Agent-Evaluator SDK 전체(33개 Config·25개 트래커)가 아니라, **Book-forge가 실제로 코드에서 쓰는 것만** 담는다 — 8장(§8.1)의 표를 Gate 관점이 아니라 에이전트 관점으로 재배열한 것이다.

## A.1 배치 평가(`@agent_eval`) — 에이전트별 전체 목록

| 에이전트 | 파일 | 데코레이터 인자 | 채점 축(Gate) | 담당 챕터 |
|---|---|---|---|---|
| PlannerAgent | `planner.py` | `goal_alignment=GoalAlignmentConfig(ignore_no_tool_tasks=False)` | A | §2, §9 |
| | | `instructions=InstructionConfig(fail_on_violation=False)` | A | §9 |
| | | `explainability=ExplainabilityConfig(min_reasoning_length=30)` | G | §9 |
| TOCDesignerAgent | `toc_designer.py` | `plan_tracking=PlanConfig()` | A | §9 |
| | | `subtask_tracking=SubtaskConfig()` | A | §9 |
| | | `context_retention=ContextRetentionConfig()` | A | §9 |
| ChapterDrafterAgent | `chapter_drafter.py` | `rag_mode=True, context_arg="sources"` | C(HallucinationDetector 자동 on) | §7, §9 |
| | | `sla=SLAConfig(p95_ms=60_000, p99_ms=90_000)` | D | §8, §9 |
| | | `threat_severity=ThreatSeverityConfig()` | E | §8 |
| ChatAgent | `chat_agent.py` | `rag_mode=True, context_arg="sources"` | C(HallucinationDetector 자동 on) | §7 |
| | | `sla=SLAConfig(p95_ms=30_000, p99_ms=60_000)` | D | §7, §8 |
| | | `threat_severity=ThreatSeverityConfig()` | E | §7, §8 |
| ReviewerAgent | `review_panel.py`(`build_reviewer`) | `agent_role=AgentRoleConfig(role_violation_penalty=0.3)` | F | §5, §8 |
| ChiefEditorAgent | `review_panel.py`(`build_chief_editor`) | `conflict_resolution=ConflictResolutionConfig()` | F | §5, §8 |
| `revise()` | `review_loop.py` | `loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3)` | B | §6, §8 |

## A.2 실시간 가드레일(`LiveGuardrail`/`tool_guard`) — 배치 평가와 분리된 축

| 사용처 | 파일 | 설정 | 막는 것 | 담당 챕터 |
|---|---|---|---|---|
| 챕터 스캐폴딩 | `scaffold.py`(`write_chapter_stub`) | `LiveGuardrail(loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=5))` | 같은 도구 호출의 5회 연속 반복 | §12 |
| 목차 개정 재조정 | `scaffold.py`(`reconcile_chapters`) | 위와 동일 | 위와 동일 | §12 |
| 웹 에디터 저장 | `editor/server.py`(`_write_chapter_file`) | `LiveGuardrail(team_concurrency=TeamConcurrencyConfig(claims_path=..., owner="auto"))` | 여러 저자의 스코프 겹침(편집 충돌) | §13 |

## A.3 정적 검증기 — Gate 점수와 무관한 별도 축

| 검증기 | 파일 | 검증 대상 | 담당 챕터 |
|---|---|---|---|
| 코드-본문 정합성 | `code_consistency_checker.py` | 본문의 백틱 심볼·import가 실제 패키지/로컬 저장소에 존재하는가 | §10 |
| 실증 가능성 검증 | `demonstration_verifier.py` | exercise/diagram/reference_table/capstone 콘텐츠가 문법적으로 유효한가 | §10 |
| 용어 일관성 검사 | `term_consistency_checker.py` | 여러 챕터가 같은 개념을 같은 표기로 부르는가 | §10 |

## A.4 모니터 수준 설정 — 프로젝트 전체에 적용

| 설정 | 위치 | 기본값 | 조정 방법 | 담당 챕터 |
|---|---|---|---|---|
| `enable_security_metrics` | `build_book_monitor()` | `True`(상시 on) | — | §9 |
| `enable_hallucination_detection` | `build_book_monitor()` | `False` | — | §9 |
| `enable_llm_judge` | `build_book_monitor()` | `False` | `--enable-llm-judge`(CLI) | §14 |
| `gate_a_tcr_weight` | `PerformanceMonitor` | `0.4` | `BOOK_FORGE_GATE_A_TCR_WEIGHT`(.env) | §9, §14 |
| `gate_c_tcr_weight` | `PerformanceMonitor` | `0.4` | `BOOK_FORGE_GATE_C_TCR_WEIGHT`(.env) | §14 |
| `gate_b_loop_weight` | `PerformanceMonitor` | `0.0` | `BOOK_FORGE_GATE_B_LOOP_WEIGHT`(.env) | §14 |

## A.5 챕터별 부재 항목 — 명시적으로 안 쓴 것

이 책의 관례(8장 §8.5)를 뒤집어, "이 책의 에이전트들이 33개 Config 중 명시적으로 안 쓰는 것"도 참고로 남긴다 — Book-forge가 아직 다루지 않는 영역을 코드 레벨에서 확인할 수 있다.

| 안 쓰는 Config/기능 | Gate | 이유(15장 참고) |
|---|---|---|
| 자동 재작성 트리거 | — | 검증 결과를 근거로 스스로 다시 쓰는 경로 부재 |
| `ScopeConfig` | B | 경로 검사는 직접 구현(§12) — 이 Config는 도구 이름 목록이라 용도가 다름 |
| 이미지 검색/배치 관련 기능 | — | Book-forge에 대응 기능 자체가 없음 |

## A.6 `narrative` 밖의 다섯 콘텐츠 유형 — 본문에서 다루지 않은 생성기 4종

이 책의 15개 챕터는 `ChapterDrafterAgent`(`content_type="narrative"`, 7·8장)를 집중적으로 다뤘다 — 목차 매니페스트(4장)가 지원하는 6개 콘텐츠 유형(`narrative`/`reference_table`/`diagram`/`exercise`/`capstone`/`module_reference`) 중 `exercise`는 같은 `draft_chapter()`가 프롬프트만 바꿔 생성하므로(8장에서 이미 확인한 `_CONTENT_TYPE_PROMPTS.get(content_type, ...)`) 별도 코드가 없지만, 나머지 넷은 각자 독립된 전용 에이전트다. 10장이 이들의 **정적 검증**(`verify_diagram()` 등)은 다뤘지만 **생성 코드 자체**는 다루지 않았다 — 여기서 그 공백을 채운다.

```python
# diagram_generator.py — mermaid 다이어그램 생성
def build_generate_diagram(llm: LLM, monitor: PerformanceMonitor) -> GenerateFn:
    @agent_eval(
        monitor, task_type="document_creation", question_arg="chapter_title",
        rag_mode=True, context_arg="sources",
        sla=SLAConfig(p95_ms=60_000, p99_ms=90_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_diagram(chapter_title, chapter_no, sources, ground_truth="") -> tuple[str, EvalMetadata]:
        prompt = DIAGRAM_PROMPT.format(chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000])
        return llm.generate(prompt, system=DIAGRAM_SYSTEM_PROMPT, max_tokens=3000), \
            EvalMetadata(extra={"phase": "diagram", "chapter_no": chapter_no})
    return generate_diagram
```

```python
# capstone_generator.py — 템플릿(TODO 포함) + 정답 코드를 한 번에 생성
def build_generate_capstone(llm: LLM, monitor: PerformanceMonitor) -> CapstoneFn:
    @agent_eval(
        monitor, task_type="document_creation", question_arg="chapter_title",
        rag_mode=True, context_arg="sources",
        # 템플릿+정답 두 부분을 한 번에 생성하므로 서술형보다 응답이 길다 — SLA도 넉넉하게.
        sla=SLAConfig(p95_ms=90_000, p99_ms=120_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_capstone(chapter_title, chapter_no, sources, ground_truth="") -> tuple[str, EvalMetadata]:
        prompt = CAPSTONE_PROMPT.format(chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000])
        return llm.generate(prompt, system=CAPSTONE_SYSTEM_PROMPT, max_tokens=3500), \
            EvalMetadata(extra={"phase": "capstone", "chapter_no": chapter_no})
    return generate_capstone
```

`ModuleReferenceAgent`가 가장 흥미로운 사례다 — `rag_mode=True`를 똑같이 쓰지만, `sources`에 RAG **검색** 결과가 아니라 4장(§4.3)의 구조적 코드 인덱싱이 만든 **전체** 모듈/클래스/함수 목록을 그대로 넣는다. 모듈 docstring이 그 이유를 실측 수치로 남겼다.

> "`reference_table.py`는 RAG로 검색된 소스 발췌문에서 '확인되는 값만' 표로 만든다 — 검색이 놓친 항목은 애초에 LLM 눈에 안 보이므로 조용히 빠진다(실측: Book-forge 자신의 `agents/` 13개 파일 중 4개만 우연히 top-k에 뽑혀 다뤄짐). 이 에이전트는 RAG 검색을 거치지 않고, H가 만든 구조 요약(모든 모듈/클래스/함수를 결정론적으로 나열)을 그대로 `sources`로 받는다."

```python
def build_generate_module_reference(llm: LLM, monitor: PerformanceMonitor) -> GenerateFn:
    @agent_eval(
        monitor, task_type="document_creation", question_arg="chapter_title",
        rag_mode=True, context_arg="sources",
        sla=SLAConfig(p95_ms=90_000, p99_ms=120_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_module_reference(chapter_title, chapter_no, sources, ground_truth="") -> tuple[str, EvalMetadata]:
        prompt = MODULE_REFERENCE_PROMPT.format(chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:8000])
        return llm.generate(prompt, system=MODULE_REFERENCE_SYSTEM_PROMPT, max_tokens=4000), \
            EvalMetadata(extra={"phase": "module_reference", "chapter_no": chapter_no})
    return generate_module_reference
```

이 넷이 전부 `rag_mode=True` + `threat_severity=ThreatSeverityConfig()` 조합을 공유한다는 사실은 8장(§8.3)의 예측을 다시 한번 확인해준다 — **외부 RAG 소스를 프롬프트에 섞는 모든 에이전트가 예외 없이 이 Config 쌍을 쓴다.** `reference_table.py`(RAG **검색** 기반, "확인되는 값만")와 `module_reference.py`(정적 인덱싱 **전체** 목록, "빠짐없이") 사이의 대조는, "같은 `rag_mode=True`라도 `sources`에 무엇이 들어오는가"가 완전히 다른 실패 모드(누락 vs 날조)를 만든다는 것을 보여준다 — `demonstration_verifier.py`가 이 둘을 반대 방향으로 검증하는 이유(10장)가 바로 여기 있다.

---

이 표는 이 책이 인용한 소스 코드 커밋(`00_기획안.md` 참고) 시점을 기준으로 한다 — 코드가 바뀌면 이 표도 낡아진다.
