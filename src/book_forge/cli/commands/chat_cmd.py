"""`book-forge chat` — 프로젝트 지식창고에 대화형으로 질의한다 (옵션, [rag] extra 필요).

일반 능력 E(독자 상호작용) — book-forge draft가 --source로 쌓아온 영속 지식창고
(knowledge/store.json)를 재사용한다. draft를 한 번도 안 돌렸으면 지식창고가
없으므로 안내 메시지와 함께 종료한다.

지속형 상호작용 강화: 세션 전체를 agent-evaluator의 ConversationSession으로
감싼다(monitor.conversation()) — 이전에는 매 질문이 완전히 독립적이라 "방금
말한 그거" 같은 이어지는 질문을 이해하지 못했다. 최근 대화 이력을 프롬프트에
포함하고, 세션 종료 시 context_retention/topic_coherence 등 4개 지표를 CLI에
표시한다(agent-evaluator 자체 신호, Gate A-G 점수에는 반영되지 않는 운영
지표 — CLAUDE.md의 25개 트래커 분류 참고).
"""
from __future__ import annotations

import click

from book_forge.cli.project_utils import load_book_config
from book_forge.config import load_config
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm

# 프롬프트에 포함할 최근 대화 턴 수 — 무한정 누적하면 컨텍스트가 계속 커진다.
_MAX_HISTORY_TURNS = 3


def _format_history(history: list[tuple[str, str]]) -> str:
    recent = history[-_MAX_HISTORY_TURNS:]
    return "\n\n".join(f"Q: {q}\nA: {a}" for q, a in recent)


@click.command()
@click.argument("slug")
@click.option("--top-k", type=int, default=6, show_default=True, help="질문마다 검색할 청크 수")
def chat(slug: str, top_k: int) -> None:
    """SLUG 프로젝트의 지식창고에 대화형으로 질문한다. /exit 로 종료."""
    try:
        import numpy  # noqa: F401
    except ImportError as exc:
        # knowledge.store 모듈 자체는 numpy를 query_with_scores() 내부에서만
        # 지연 import하므로, 모듈 import만으로는 [rag] extra 미설치를 못 잡는다.
        raise click.ClickException(
            'RAG 기능에 필요한 패키지가 없습니다. pip install -e ".[rag]" 로 설치하세요.'
        ) from exc

    from book_forge.knowledge.store import KnowledgeStore, default_store_path

    load_config()
    config = load_book_config(slug)

    store_path = default_store_path(config.project_dir)
    if not store_path.is_file():
        raise click.ClickException(
            f"지식창고가 없습니다: {store_path}\n"
            "book-forge draft <slug> <chapter_no> --source ... 를 먼저 실행해 소스를 쌓으세요."
        )
    store = KnowledgeStore.load(store_path)

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    from book_forge.agents.chat_agent import build_answer_question
    from book_forge.eval.monitor import build_book_monitor

    monitor = build_book_monitor(output_dir=str(config.project_dir / "eval_results"))
    answer_question = build_answer_question(llm, monitor)

    click.echo(f"💬 {config.title} 지식창고 Q&A ({len(store)}개 청크). /exit 로 종료.\n")

    history: list[tuple[str, str]] = []
    conv = monitor.conversation(f"chat_{slug}")
    try:
        with conv:
            while True:
                try:
                    question = click.prompt("질문", prompt_suffix="> ")
                except (EOFError, click.exceptions.Abort):
                    break
                stripped = question.strip()
                if stripped.lower() in {"/exit", "/quit"}:
                    break
                if not stripped:
                    continue

                scored = store.query_with_scores(stripped, top_k=top_k)
                if not scored:
                    click.echo("(지식창고에서 관련 내용을 찾지 못했습니다)\n")
                    continue

                sources_text = "\n\n---\n\n".join(chunk for chunk, _ in scored)
                answer = answer_question(
                    question=stripped,
                    sources=sources_text,
                    conversation_history=_format_history(history),
                    ground_truth=stripped,
                )
                click.echo(f"\n{answer}\n")
                history.append((stripped, answer))
                conv.turn(user=stripped, agent=answer)
    finally:
        monitor.save_to_file("chat")

    if conv.metrics is not None:
        m = conv.metrics
        click.echo("📊 이 대화 세션의 지속형 상호작용 지표 (참고용):")
        click.echo(f"   턴 수: {m.turn_count}  |  종합: {m.overall_score:.2f}")
        click.echo(
            f"   맥락 유지: {m.context_retention:.2f}  |  주제 일관성: {m.topic_coherence:.2f}  |  "
            f"심화도: {m.progressive_depth:.2f}  |  완결성: {m.session_completion:.2f}"
        )
