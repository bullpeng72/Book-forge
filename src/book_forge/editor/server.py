"""Book-forge 웹 에디터 — Part/Chapter MD 트리 + 이미지 갤러리.

Book/AOO의 edit_book.py는 "완성된 단일 HTML을 섹션 단위로 편집"하는 방식으로
lecture_forge.editor.server를 재사용했다. Book-forge는 프로젝트 구조 자체가
Part/Chapter별 개별 마크다운 파일이므로, 편집 대상도 그 원본 마크다운
파일이어야 한다 — 완성 HTML이 아니라 소스를 직접 고치는 구조로 새로 설계했다.

경로 안전성: 클라이언트는 항상 chapter_no(정수)로만 챕터를 지칭한다. 실제
파일 경로는 서버가 매 요청마다 book_forge.publish.toc_loader.load_toc()로
재조회해 검증된 ResolvedChapter에서만 얻는다 — 이미지 서빙 라우트만 예외적으로
part 디렉토리 이름을 URL로 받으므로, 목차에 실제 존재하는 이름인지 허용 목록
검사 + 경로 포함 검사를 이중으로 한다(scaffold.py의 경로 방어와 동일 원칙).

팀 동시성(M6): 저장은 LiveGuardrail(team_concurrency=...)을 거친다.
공동 저자는 (agent-evaluator에 이미 있는) `agent-eval claims add <절대경로>
--developer <이름>`으로 자신이 작업할 Part 디렉토리를 미리 선점(claim)해두면,
다른 저자가 같은 스코프를 저장하려 할 때 409로 차단된다 — 새 클레임 관리
로직을 만들지 않고 SDK의 `.aoo/claims.jsonl` 관례를 프로젝트 디렉토리
안(`<project>/.aoo/claims.jsonl`)에 그대로 재사용한다.
"""
from __future__ import annotations

from pathlib import Path
from threading import Timer
from typing import Optional

from agent_evaluator.gates.live_guardrail import (
    GuardrailBlockedError,
    LiveGuardrail,
    live_guardrail_session,
    tool_guard,
)
from agent_evaluator.gates.team_concurrency import TeamConcurrencyConfig

from book_forge.publish.config import BookConfig
from book_forge.publish.toc_loader import ResolvedChapter, load_toc

_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

_INDEX_HTML_PATH = Path(__file__).parent / "templates" / "index.html"


def _find_chapter(project_dir: Path, chapter_no: int) -> Optional[ResolvedChapter]:
    for rc in load_toc(project_dir):
        if rc.spec.chapter_no == chapter_no:
            return rc
    return None


@tool_guard(tool_name="write", audit_blocked=True)
def _write_chapter_file(path: str, content: str) -> str:
    """실제 파일 쓰기. 매개변수 이름 ``path``는 TeamConcurrencyConfig의
    path_param_candidates 기본값과 일치해야 스코프 충돌 검사가 인자에서
    경로를 뽑아낼 수 있다."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")
    return "ok"


def _team_guardrail(project_dir: Path) -> LiveGuardrail:
    claims_path = project_dir / ".aoo" / "claims.jsonl"
    return LiveGuardrail(
        team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path), owner="auto")
    )


def create_app(config: BookConfig):
    from flask import Flask, jsonify, request, send_from_directory  # lazy import — [serve] extra

    app = Flask(__name__)
    project_dir = config.project_dir

    @app.get("/")
    def index():
        html = _INDEX_HTML_PATH.read_text(encoding="utf-8")
        return html.replace("__TITLE__", config.title)

    @app.get("/api/toc")
    def api_toc():
        chapters = load_toc(project_dir)
        return jsonify(
            [
                {
                    "part_no": rc.spec.part_no,
                    "part_title": rc.spec.part_title,
                    "chapter_no": rc.spec.chapter_no,
                    "chapter_title": rc.spec.chapter_title,
                    "exists": rc.exists,
                }
                for rc in chapters
            ]
        )

    @app.get("/api/chapter/<int:chapter_no>")
    def api_get_chapter(chapter_no: int):
        rc = _find_chapter(project_dir, chapter_no)
        if rc is None:
            return jsonify({"error": "챕터를 찾을 수 없습니다"}), 404
        content = rc.path.read_text(encoding="utf-8") if rc.exists else ""
        return jsonify({"content": content})

    @app.put("/api/chapter/<int:chapter_no>")
    def api_put_chapter(chapter_no: int):
        rc = _find_chapter(project_dir, chapter_no)
        if rc is None:
            return jsonify({"error": "챕터를 찾을 수 없습니다"}), 404
        body = request.get_json(silent=True) or {}
        content = body.get("content", "")

        guardrail = _team_guardrail(project_dir)
        try:
            with live_guardrail_session(guardrail, task_id=f"edit_ch{chapter_no}"):
                _write_chapter_file(path=str(rc.path), content=content)
        except GuardrailBlockedError as exc:
            return jsonify({"error": f"편집 충돌: {exc.verdict.reason}"}), 409

        return jsonify({"saved": True})

    @app.post("/api/preview")
    def api_preview():
        from book_forge.publish.markdown_engine import embed_images_as_data_uri, md_to_html

        body = request.get_json(silent=True) or {}
        content = body.get("content", "")
        chapter_no = body.get("chapter_no")
        html_body = md_to_html(content)
        rc = _find_chapter(project_dir, chapter_no) if chapter_no else None
        if rc is not None:
            html_body = embed_images_as_data_uri(html_body, rc.path.parent)
        return jsonify({"html": html_body})

    @app.get("/api/chapter/<int:chapter_no>/images")
    def api_list_images(chapter_no: int):
        rc = _find_chapter(project_dir, chapter_no)
        if rc is None:
            return jsonify({"error": "챕터를 찾을 수 없습니다"}), 404
        images_dir = rc.path.parent / "images"
        if not images_dir.is_dir():
            return jsonify([])
        files = sorted(p.name for p in images_dir.iterdir() if p.suffix.lower() in _ALLOWED_IMAGE_EXTS)
        return jsonify(
            [{"name": name, "url": f"/images/{rc.spec.part_dir_name}/{name}"} for name in files]
        )

    @app.post("/api/chapter/<int:chapter_no>/images")
    def api_upload_image(chapter_no: int):
        rc = _find_chapter(project_dir, chapter_no)
        if rc is None:
            return jsonify({"error": "챕터를 찾을 수 없습니다"}), 404
        file = request.files.get("file")
        if file is None or not file.filename:
            return jsonify({"error": "파일이 없습니다"}), 400
        # 디렉토리 구분자를 제거해 업로드 파일명으로 인한 경로 조작을 막는다.
        safe_name = Path(file.filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in _ALLOWED_IMAGE_EXTS:
            return jsonify({"error": f"지원하지 않는 확장자: {suffix}"}), 400
        images_dir = rc.path.parent / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        file.save(images_dir / safe_name)
        return jsonify({"name": safe_name, "url": f"/images/{rc.spec.part_dir_name}/{safe_name}"})

    @app.get("/images/<path:part_dir_name>/<path:filename>")
    def serve_image(part_dir_name: str, filename: str):
        valid_part_dirs = {rc.spec.part_dir_name for rc in load_toc(project_dir)}
        if part_dir_name not in valid_part_dirs:
            return jsonify({"error": "잘못된 경로"}), 404
        images_dir = (project_dir / part_dir_name / "images").resolve()
        if project_dir.resolve() not in images_dir.parents:
            return jsonify({"error": "잘못된 경로"}), 404
        return send_from_directory(images_dir, filename)

    return app


def run_editor(config: BookConfig, *, port: int = 5858, open_browser: bool = True) -> None:
    import webbrowser

    app = create_app(config)
    if open_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(port=port, debug=False)
