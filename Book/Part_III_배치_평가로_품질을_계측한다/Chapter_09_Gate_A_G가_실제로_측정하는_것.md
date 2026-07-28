# Chapter 9. Gate A–G 관점에서 다시 본다

> **이 챕터에서 배우는 것**
> - Tracker·Config·Gate — 지금까지 뒤섞어 써온 세 용어가 실제로는 서로 다른 층이라는 것
> - 8장의 16개 컴포넌트 표를 **Gate 축**으로 뒤집으면 무엇이 보이는지 — 어느 Gate가 파이프라인의 어느 단계에서 개입하는가
> - 7개 Gate(A–G) 중 Book-forge가 실제로 값을 채우는 것은 몇 개인지, 왜 어떤 Gate는 자주 "N/A"로 나오는지
> - 한 챕터를 실제로 채점해보면 어떤 숫자가 나오는지

> **이런 분이 먼저 읽으면 좋습니다**: 8장에서 "이 에이전트가 무엇을 재는가"는 컴포넌트 단위로 봤지만, "그래서 Gate A는 정확히 무엇으로 채워지는가"처럼 Gate를 기준으로 거꾸로 보고 싶은 분. "58개 지표, 7개 Gate"라는 Agent-Evaluator SDK의 전체 규모에 압도됐지만, 실제 프로젝트 하나가 그중 정확히 무엇을 쓰는지 궁금한 분도 이 챕터부터 시작하면 된다.

---

## 9.1 Tracker · Config · Gate — 2장에서 본 세 층을 코드로 증명한다

2장(§2.1)이 이미 Tracker·Config·Gate 세 층의 정의와 "Config를 하나도 안 켜도 Tracker는 이미 켜져 있다"는 결론을 미리 보여줬다. 이 절은 그 주장을 뒷받침하는 **실제 코드**를 처음으로 연다.

`eval/monitor.py`의 `build_book_monitor()`가 `PerformanceMonitor`를 만드는 순간, SDK 내부에서는 이미 이런 일이 일어난다(Agent-Evaluator SDK의 `core/trackers/monitor.py` 실제 초기화 코드).

> 🔧 **Agent-Evaluator SDK 소스**: `agent_evaluator/core/trackers/monitor.py` (`PerformanceMonitor.__init__()`, Book-forge 코드가 아니다)

```python
# PerformanceMonitor.__init__() 내부 — 에이전트가 무엇을 하든 상관없이 항상 실행된다
self.tcr_tracker = TaskCompletionTracker()
self.latency_tracker = LatencyTracker()
self.token_tracker = TokenEconomyTracker(pricing)
self.agent_coordination_tracker = AgentCoordinationTracker()
```

`ChatAgent`(7장)의 `@agent_eval`에는 `SLAConfig`만 있고 `AgentRoleConfig`는 없지만, `agent_coordination_tracker`는 여전히 존재한다. 다만 아무도 `track_interaction()`을 호출하지 않았을 뿐이다(8장 §8.4의 ReviewerAgent만 이 메서드를 부른다). **Config는 "이 Tracker를 켠다"가 아니라 "이미 켜져 있는 Tracker의 판정 기준을 조정한다"에 가깝다.**

Tracker 하나가 실제로 어떻게 동작하는지 `LatencyTracker`로 확인해보면 이 층의 정체가 뚜렷해진다.

> 🔧 **Agent-Evaluator SDK 소스**: `agent_evaluator/core/trackers/layer1.py` (Book-forge 코드가 아니다)

```python
class LatencyTracker(BaseTracker):
    def record_latency(self, task_id: str, task_type: str,
                       total_time: float, breakdown: dict[str, float]):
        """Record latency for a task"""
        self._latencies.append({
            "task_id": task_id, "task_type": task_type,
            "total_time": total_time, "breakdown": breakdown,
        })

    def get_latency_stats(self, task_type: str | None = None) -> dict[str, float]:
        """p50/p95/p99 등 지연 통계를 계산해 돌려준다."""
        ...
```

`record_latency()`가 매 호출마다 숫자를 쌓고(수집), `get_latency_stats()`가 그 누적치에서 p95·p99 같은 통계를 뽑는다(집계). **모든 Tracker가 이 "쌓기 → 계산하기" 두 메서드 쌍 패턴을 공유한다.** Gate가 최종적으로 읽는 것은 원시 데이터가 아니라 이 `get_*_stats()`/`calculate_*()` 메서드들이 이미 계산해 둔 값이다.

`SLAConfig`가 실제로 Tracker의 결과를 어떻게 조정하는지도 정의를 보면 분명해진다.

> 🔧 **Agent-Evaluator SDK 소스**: `agent_evaluator/gates/gate_d_performance/configs.py` (Book-forge 코드가 아니다)

```python
@dataclass
class SLAConfig:
    """SLA 준수 추적 설정."""
    p95_ms: float = 5000.0
    p99_ms: float = 10000.0
    breach_window: int = 10
    warn_threshold: int = 2
    fail_threshold: int = 5
    max_cost_per_task: float | None = None
```

`p95_ms`/`p99_ms`는 각각 "상위 95%/99% 요청이 이 시간 안에 끝나야 한다"는 지연 기준선이다. 8장 §8.3의 `ChapterDrafterAgent`가 `SLAConfig(p95_ms=60_000, p99_ms=90_000)`를 넘기는 것은, `LatencyTracker`가 이미 계산해 둔 p95·p99 값을 "이 숫자를 넘으면 위반"이라는 기준과 대조하라고 Gate D에 알려주는 것이다. `LatencyTracker` 자신은 `SLAConfig`가 있는지 없는지조차 모른다. **Tracker는 "무슨 일이 있었는가"를 객관적으로 기록하고, Config는 "그게 괜찮은 일이었는가"를 판단할 기준선을 정하고, Gate는 그 판단들을 모아 하나의 점수로 압축한다.**

## 9.2 8장의 표를 뒤집는다 — Gate가 파이프라인의 어디에서 개입하는가

8장은 컴포넌트를 행으로 놓고 "무엇을 재는가"를 열로 봤다. 이 절은 그 표를 90도 돌려, **Gate를 행으로** 놓는다. Agent-Evaluator SDK 전체는 25개 네이티브 트래커와 33개 Harness Config를 제공하지만, Book-forge의 16개 컴포넌트가 **실제로 건드리는** 것만 정리하면 이렇다.

| Gate | Book-forge가 채우는 값 | 파이프라인의 어느 단계에서 개입하는가 |
|---|---|---|
| **A** 목표 달성 | `TaskCompletionTracker` + `AccuracyEvaluator` 블렌딩(0.4×TCR + 0.6×Accuracy) | **전체 배치 파이프라인** — `TaskCompletionTracker`(TCR)는 `@agent_eval`이 붙은 14개 컴포넌트 전부에서 항상 기록된다(§9.1). Accuracy 블렌딩은 의미 있는 `ground_truth`를 넘기는 곳에서 특히 뚜렷하다 — **기획·목차 단계**(8장 §8.2)의 Planner·`revise()`·TOCDesigner가 대표적 |
| **B** 행동 무결성 | `LoopDetectionConfig` 기반 반복 탐지 | **승인 루프**(§8.2) — `revise()`만. 나머지 15개는 대부분 N/A |
| **C** 신뢰성 | `HallucinationDetector`(RAG 근거 대조) | **콘텐츠 생성 단계**(§8.3)의 5개 RAG 생성기 + **대화 단계**(§8.4)의 ChatAgent — `rag_mode=True`인 6개 전부 |
| **D** 성능 계약 | `LatencyTracker`(항상) + `SLAConfig` 위반 여부 | **전체 파이프라인** — LatencyTracker는 컴포넌트와 무관하게 항상 기록하지만, 기준선(`SLAConfig`)이 있는 곳만 Gate D 점수에 실제로 반영 |
| **E** 보안 경계 | 5개 보안 트래커 + `ThreatSeverityConfig` | **콘텐츠 생성·대화 단계**(§8.3·§8.4) — `rag_mode=True`인 6개가 명시적, 나머지는 `enable_security_metrics=True`로 상시 on |
| **F** 다중 에이전트 | `AgentCoordinationTracker` + `ConflictResolutionConfig` | **검토 단계**(§8.4) — ReviewerAgent·ChiefEditorAgent만. Book-forge에서 유일하게 값이 나오는 지점 |
| **G** 관측성 | `ExplainabilityConfig` | **기획 단계**(§8.2)의 PlannerAgent, **생성 단계**(§8.3)의 AlternativeSuggester, **부가 단계**(§8.5)의 SlideCondenser — 3곳이 명시적, 나머지는 대부분 N/A |

이 표를 8장의 표와 나란히 놓으면, 같은 사실을 두 방향에서 확인하는 셈이 된다. 8장은 "PlannerAgent가 무엇을 재는가"(행 하나)를 물었고, 이 표는 "Gate A가 어디서 채워지는가"(열 하나)를 묻는다. Gate A·D는 TCR·LatencyTracker가 항상 켜져 있는 만큼 전 파이프라인에 걸쳐 값을 얻지만, 나머지 Gate는 뚜렷하게 갈린다. **Gate G는 기획·생성·부가 단계 3곳에만, Gate C/E는 콘텐츠 생성·대화 단계에만, Gate F는 검토 단계 한 곳에만** 값이 채워진다 — 이 비대칭 자체가 Book-forge라는 특정 파이프라인의 성격을 그대로 드러낸다. 순차 파이프라인이 압도적으로 많고(4장) 감독자-작업자 협업(5장)은 리뷰 패널 한 곳뿐이므로, Gate F도 딱 그만큼만 값을 얻는다.

## 9.3 "N/A"가 버그가 아니라 정직한 신호인 이유

이 표를 처음 보면 Gate B·F·G가 유독 자주 비어 보인다는 인상을 받을 수 있다. 이건 계측 누락이 아니라 **그 Gate가 실제로 측정할 신호 자체가 그 태스크에 없기 때문**이다.

- Gate F(다중 에이전트)는 `AgentCoordinationTracker`가 `track_interaction()` 호출을 필요로 한다(8장 §8.4). PlannerAgent 하나만 도는 태스크에는 애초에 "다른 에이전트와의 상호작용"이라는 사건 자체가 없다. N/A가 정직한 답이다.
- Gate B(행동 무결성)의 루프 탐지도 마찬가지다. 한 번만 호출되는 함수에는 "반복"이라는 개념이 성립하지 않는다.

`monitor.py`(agent-evaluator SDK)의 원칙이 정확히 이렇다. 데이터가 없는 Gate는 억지로 기본값(예: 1.0이나 0.5)을 채우지 않고 N/A로 남긴다. **거짓으로 만점을 주는 것보다 "측정하지 않았다"고 정직하게 말하는 편이, 이후 그 Gate 점수를 신뢰할지 판단하는 사람에게 더 유용하다.**

## 9.4 Gate A의 실제 계산 — TCR과 Accuracy를 섞는다

Gate A는 이 책이 가장 자주 언급하는 Gate다(PlannerAgent·TOCDesignerAgent·ChapterDrafterAgent 전부 기여). 실제 점수 계산은 다음 공식을 따른다(`CLAUDE.md`에 문서화된 Book-forge 전역 설정).

> 📄 **출처**: `Book-forge/CLAUDE.md`에 문서화된 공식(실제 소스 코드 발췌가 아니라 개발자가 문서로 정리해둔 수식)

```
_a_score = gate_a_tcr_weight × TCR컴포넌트 + (1 − gate_a_tcr_weight) × 나머지 평균
```

기본값은 `gate_a_tcr_weight=0.4`다. 태스크 완료율(TCR)이 40%, 나머지(AccuracyEvaluator 블렌딩·ResponseQualityEvaluator 등)가 60%를 차지한다. 16장에서 이 가중치를 프로젝트마다 다르게 조정하는 실제 코드(`.env`)를 다룬다.

## 9.5 실제 채점 사례 — 한 챕터의 Gate 점수

이 책을 준비하며 실제로 `book-forge new --source ...`로 챕터 하나를 생성했을 때 나온 실제 로그다(이 세션의 실제 실행 기록).

> 🖥️ **실행 로그**: `book-forge draft` 실제 실행 결과 출력(소스 코드가 아니라 이 세션에서 재현된 터미널 로그)

```
📈 이 초안의 Gate 점수 (참고용 — 전체 판정은 book-forge gate로):
  ⚠️  A (목표 달성): 0.663
  · B (행동 무결성): N/A
  ✅ C (신뢰성): 0.708
  ❌ D (성능 계약): 0.135
  ✅ E (보안 경계): 1.000
  · F (다중 에이전트): N/A
  ⚠️  G (관측성): 0.694
```

이 예시가 §9.3의 주장을 그대로 뒷받침한다. B·F는 N/A인데, 이 태스크(ChapterDrafterAgent 단독 호출)에 반복이나 다중 에이전트 상호작용이 없었기 때문이다 — §9.2 표에서 B는 승인 루프에만, F는 검토 단계에만 값이 있다는 것과 정확히 일치한다. D는 0.135로 낮게 나왔다. 로컬 35B 모델이 SLA 60초 기준을 자주 초과했기 때문인데, 로컬 추론의 실제 트레이드오프인 셈이다(8장 §8.3에서 이미 예고한 사례). E는 1.000인데, 이는 "보안이 완벽하다"는 뜻이라기보다 이 특정 태스크에서 5개 보안 트래커가 위반을 하나도 못 찾았다는 뜻이다. Gate 점수는 항상 **그 태스크에서 실제로 검사한 것에 한해서만** 유효하다.

이 아이콘(✅/⚠️/❌/·)이 어디서 나오는지도 코드로 확인할 수 있다 — `eval/gate_summary.py`의 `format_gate_line()`이 한 Gate의 점수 하나를 받아 이 형식의 문자열 한 줄로 바꾼다.

> 📄 **파일**: `src/book_forge/eval/gate_summary.py`

```python
def format_gate_line(gate: str, score: Optional[float]) -> str:
    label = GATE_LABELS.get(gate, gate)
    if score is None:
        return f"  · {gate} ({label}): N/A"
    if score >= 0.7:
        icon = "✅"
    elif score >= 0.5:
        icon = "⚠️ "
    else:
        icon = "❌"
    return f"  {icon} {gate} ({label}): {score:.3f}"
```

기준선은 단순하다. 0.7 이상은 ✅, 0.5~0.7은 ⚠️, 0.5 미만은 ❌, `None`(N/A)은 `·`다. 이 함수는 Gate 점수를 계산하지 않는다. 이미 계산된 `score`를 사람이 한눈에 읽을 수 있는 표시로만 바꿀 뿐이다(계산과 표시를 분리하는 흔한 패턴). `draft_cmd.py`가 챕터 하나를 생성한 직후 이 함수를 Gate A~G 각각에 대해 호출해, 위에서 본 실제 로그를 만든다.

> ⚠️ **N/A와 낮은 점수를 혼동하지 말 것**: `N/A`는 "측정 대상이 아니었다"이고, `0.135`(D)는 "측정했고, 기준을 못 넘었다"다. 이 둘을 같은 것으로 취급해 평균에 섞으면 안 된다. 실제로 `HarnessEvaluationGate`는 데이터 없는 Gate를 평균에서 제외한다.

---

## 직접 해보기

1장(§1.9)에서 실행한 `book-forge gate`의 실제 출력을 다시 열어, §9.2의 Gate별 표와 나란히 놓고 대조해보자. 화면에 찍힌 각 줄(`A (목표 달성): 0.663` 등)이 파이프라인의 어느 단계에서 나온 값인지, 8장의 어느 절(§8.2~8.5)로 거슬러 올라가는지 하나씩 짚어낼 수 있다면 이 챕터를 제대로 소화한 것이다. N/A로 나온 Gate가 있다면 왜 N/A인지(§9.3)도 함께 설명해보라.

## 이 챕터의 핵심

- **Tracker(항상 켜짐) → Config(에이전트별 판정 기준 조정, 옵트인) → Gate(A–G 최종 점수, 집계)는 서로 다른 층이다.**
- **8장의 컴포넌트 축과 9장의 Gate 축은 같은 사실을 다른 방향에서 본다.** Gate A·D는 전 파이프라인에서, Gate G는 기획·생성·부가 단계에서, Gate C/E는 콘텐츠 생성·대화 단계에서, Gate F는 검토 단계 한 곳에서만 값이 채워진다는 비대칭이 이 파이프라인의 성격을 보여준다.
- **N/A는 결함이 아니라 정직함이다.** "이 태스크에는 이 Gate가 측정할 신호 자체가 없었다"는 뜻이다.
- **Gate A는 TCR과 Accuracy를 가중 평균한다(기본 0.4:0.6).** 이 가중치는 조정 가능하다(16장).
- **실측 사례에서 Gate D(성능)가 자주 낮게 나온다.** 로컬 모델의 지연 시간이 SLA 기준을 넘기는 경우가 실제로 있다.

## 참고 자료

- 8장 — 이 챕터가 Gate 축으로 재편성한 원본 컴포넌트별 표
- 부록 B.1·B.2(업계 동향) — 환각 탐지·에이전트 관측성이 업계 전체에서는 어떤 규모·이름으로 다뤄지는지
- `Agent-Evaluator/CLAUDE.md` — Gate별 트래커 기여 방식 전체 표
- `Agent-Evaluator/agent_evaluator/core/trackers/monitor.py` — `PerformanceMonitor.__init__()`의 Tracker 초기화
- `src/book_forge/eval/monitor.py` — `build_book_monitor()`
- `src/book_forge/eval/gate_summary.py` — `format_gate_line()`, `GATE_LABELS`

---

> **다음 챕터**는 Gate A–G가 손대지 않는 영역 — LLM을 아예 호출하지 않는 순수 정적 검증기 3종을 다룬다.
