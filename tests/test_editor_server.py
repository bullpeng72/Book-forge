"""editor/server.py — create_app() 테스트 (Flask test_client, 실제 서버 바인딩 없음)."""
import io
import json
from pathlib import Path

import pytest

pytest.importorskip("flask")

from book_forge.editor.server import create_app  # noqa: E402
from book_forge.publish.config import BookConfig  # noqa: E402


@pytest.fixture
def client(sample_project: Path):
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    app = create_app(config)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_returns_title(client) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "샘플 도서" in res.get_data(as_text=True)


def test_api_toc_lists_chapters(client) -> None:
    res = client.get("/api/toc")
    data = res.get_json()
    assert len(data) == 2
    assert data[0]["chapter_title"] == "서론"
    assert data[0]["exists"] is True


def test_api_get_chapter_returns_content(client) -> None:
    res = client.get("/api/chapter/1")
    assert res.status_code == 200
    assert "본문입니다" in res.get_json()["content"]


def test_api_get_chapter_unknown_returns_404(client) -> None:
    res = client.get("/api/chapter/999")
    assert res.status_code == 404


def test_api_put_chapter_saves_content(client, sample_project: Path) -> None:
    res = client.put("/api/chapter/1", json={"content": "# 새 내용"})
    assert res.status_code == 200
    assert res.get_json()["saved"] is True
    saved = (sample_project / "Part_1_기초" / "Chapter_01_서론.md").read_text(encoding="utf-8")
    assert saved == "# 새 내용"


def test_api_put_chapter_blocked_by_conflicting_team_claim(client, sample_project: Path) -> None:
    """다른 저자가 같은 Part 스코프를 미리 claim(agent-eval claims add 관례)해두면
    저장이 409로 차단돼야 한다 — LiveGuardrail(team_concurrency=...) 실제 동작 검증."""
    claims_dir = sample_project / ".aoo"
    claims_dir.mkdir()
    part_dir_path = str(sample_project / "Part_1_기초")  # _write_chapter_file의 path 인자와 같은 문자열 형태
    claim = {
        "claim_id": "c-test1",
        "developer": "other-author-xyz",
        "scope": [part_dir_path],
        "status": "active",
    }
    (claims_dir / "claims.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")

    res = client.put("/api/chapter/1", json={"content": "# 충돌 시도"})
    assert res.status_code == 409
    assert "편집 충돌" in res.get_json()["error"]

    # 실제로 파일이 변경되지 않았어야 한다.
    saved = (sample_project / "Part_1_기초" / "Chapter_01_서론.md").read_text(encoding="utf-8")
    assert "충돌 시도" not in saved


def test_api_put_chapter_unaffected_by_released_claim(client, sample_project: Path) -> None:
    """status가 released면 활성 클레임이 아니므로 저장이 정상 진행돼야 한다."""
    claims_dir = sample_project / ".aoo"
    claims_dir.mkdir()
    part_dir_path = str(sample_project / "Part_1_기초")
    claim = {
        "claim_id": "c-test2",
        "developer": "other-author-xyz",
        "scope": [part_dir_path],
        "status": "released",
    }
    (claims_dir / "claims.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")

    res = client.put("/api/chapter/1", json={"content": "# 정상 저장"})
    assert res.status_code == 200


def test_api_preview_renders_html(client) -> None:
    res = client.post("/api/preview", json={"content": "# 제목", "chapter_no": 1})
    assert res.status_code == 200
    assert "<h1" in res.get_json()["html"]


def test_api_list_images_returns_existing_image(client) -> None:
    res = client.get("/api/chapter/1/images")
    images = res.get_json()
    assert len(images) == 1
    assert images[0]["name"] == "sample.png"
    assert images[0]["url"] == "/images/Part_1_기초/sample.png"


def test_api_upload_image_sanitizes_path_traversal_filename(client, sample_project: Path) -> None:
    data = {"file": (io.BytesIO(b"\x89PNG\r\n\x1a\n fake"), "../../evil.png")}
    res = client.post(
        "/api/chapter/1/images", data=data, content_type="multipart/form-data"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["name"] == "evil.png"  # 디렉토리 구분자가 제거됨
    assert (sample_project / "Part_1_기초" / "images" / "evil.png").is_file()
    assert not (sample_project.parent / "evil.png").exists()  # 프로젝트 밖으로 탈출하지 않았는지


def test_api_upload_image_rejects_disallowed_extension(client) -> None:
    data = {"file": (io.BytesIO(b"not an image"), "malware.exe")}
    res = client.post(
        "/api/chapter/1/images", data=data, content_type="multipart/form-data"
    )
    assert res.status_code == 400


def test_serve_image_returns_file(client) -> None:
    res = client.get("/images/Part_1_기초/sample.png")
    assert res.status_code == 200


def test_serve_image_rejects_unknown_part_dir(client) -> None:
    res = client.get("/images/../../etc/images/passwd")
    assert res.status_code == 404
