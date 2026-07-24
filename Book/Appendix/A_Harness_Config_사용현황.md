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
| ChatAgent | `chat_agent.py` | `rag_mode=True, context_arg="sources"` | C | §7 |
| | | `sla=SLAConfig(p95_ms=30_000, p99_ms=60_000)` | D | §8 |
| ReviewerAgent | `review_panel.py`(`build_reviewer`) | `agent_role=AgentRoleConfig(role_violation_penalty=0.3)` | F | §5, §8 |
| ChiefEditorAgent | `review_panel.py`(`build_chief_editor`) | `conflict_resolution=ConflictResolutionConfig()` | F | §5, §8 |
| ReviseAgent | `review_loop.py` | `loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3)` | B | §6, §8 |

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

---

이 표는 이 책이 인용한 소스 코드 커밋(`00_기획안.md` 참고) 시점을 기준으로 한다 — 코드가 바뀌면 이 표도 낡아진다.
