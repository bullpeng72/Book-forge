#!/usr/bin/env python3
"""Book/AOO(하드코딩된 ORDERED_FILES 기반 구조) → Book-forge 프로젝트 마이그레이션.

한 번 쓰고 마는 유틸리티다 — Book-forge M2 로드맵의 "Book/AOO 마이그레이션
스크립트" 항목. 다음을 자동화한다:

  1. 소스의 build_*.py를 동적 import해 ORDERED_FILES를 읽고, Part_*/Chapter_*.md
     패턴에 맞는 파일만 걸러 챕터 번호를 책 전체 기준으로 순차 재부여한다.
     (README.md/00_서문.md/00_기획안.md/Skills 등 챕터가 아닌 파일은 목차에
     포함하지 않는다 — 00_서문.md는 참고용으로 프로젝트 루트에 그대로 복사만 한다.)
  2. 각 챕터 파일 + 같은 Part 안의 images/ 디렉토리를 새 프로젝트의
     ChapterSpec 계산 경로(book_forge.models.ChapterSpec)로 복사한다 — 이미지
     참조가 `./images/...` 상대경로이므로 파일 내용을 고칠 필요가 없다.
  3. 매칭되는 MERMAID_INJECTIONS 항목을 앵커 헤딩 바로 뒤에 원문 그대로
     삽입한다(@@HTML_START@@ 마커가 이미 포함돼 있으므로 그대로 붙여넣기만
     하면 된다). 매칭되지 않는 항목(README 등 챕터가 아닌 파일 대상)은
     건너뛰고 콘솔에 알린다 — 자동 반영하지 않는다.

사용법:
    python scripts/migrate_legacy_book.py \\
        --source /path/to/Agent-Evaluator/Media/Book \\
        --build-module build_book \\
        --target-slug agent-evaluator-harness-book

    python scripts/migrate_legacy_book.py \\
        --source /path/to/Agent-Evaluator/Media/AOO \\
        --build-module build_aoo_book \\
        --target-slug aoo-playbook
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from book_forge.config import ensure_project_dir  # noqa: E402
from book_forge.models import ChapterSpec  # noqa: E402

_PART_DIR_RE = re.compile(r"^Part_([IVXLC]+|\d+)_(.+)$")
_CHAPTER_FILE_RE = re.compile(r"^Chapter_(\d+)_(.+)\.md$")
_H1_TITLE_RE = re.compile(r"^#\s*Chapter\s*\d+\s*[:.]?\s*(.+)$", re.MULTILINE)

_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
}


def _load_build_module(source_dir: Path, module_name: str):
    """소스의 build_*.py를 실행하지 않고(모듈은 __main__ 가드로 보호돼 있음)
    ORDERED_FILES/MERMAID_INJECTIONS만 얻기 위해 동적 import한다."""
    module_path = source_dir / f"{module_name}.py"
    if not module_path.is_file():
        raise SystemExit(f"❌ 빌드 모듈을 찾을 수 없습니다: {module_path}")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _part_no_and_title(dirname: str) -> tuple[int, str] | None:
    m = _PART_DIR_RE.match(dirname)
    if not m:
        return None
    raw_no, title = m.group(1), m.group(2)
    part_no = _ROMAN_MAP.get(raw_no)
    if part_no is None:
        try:
            part_no = int(raw_no)
        except ValueError:
            return None
    return part_no, title


def _chapter_title(md_path: Path, fallback: str) -> str:
    text = md_path.read_text(encoding="utf-8")
    m = _H1_TITLE_RE.search(text)
    return m.group(1).strip() if m else fallback


def collect_chapters(ordered_files: list[Path]) -> list[tuple[ChapterSpec, Path]]:
    """ORDERED_FILES 중 Part_*/Chapter_*.md 패턴만 골라 책 전체 기준 챕터 번호를 재부여한다."""
    result: list[tuple[ChapterSpec, Path]] = []
    next_chapter_no = 1
    for fpath in ordered_files:
        if not fpath.exists():
            continue
        part_info = _part_no_and_title(fpath.parent.name)
        chapter_m = _CHAPTER_FILE_RE.match(fpath.name)
        if part_info is None or chapter_m is None:
            continue  # README/00_서문/00_기획안/Skills 등 — 챕터가 아님
        part_no, part_title = part_info
        chapter_title = _chapter_title(fpath, fallback=chapter_m.group(2).replace("_", " "))
        spec = ChapterSpec(
            part_no=part_no,
            part_title=part_title,
            chapter_no=next_chapter_no,
            chapter_title=chapter_title,
        )
        result.append((spec, fpath))
        next_chapter_no += 1
    return result


def build_toc_manifest(chapters: list[ChapterSpec]) -> str:
    lines = ["# 목차\n"]
    last_part = None
    for spec in chapters:
        if spec.part_no != last_part:
            lines.append(f"\n## Part {spec.part_no}. {spec.part_title}\n")
            last_part = spec.part_no
        lines.append(f"- Chapter {spec.chapter_no}. {spec.chapter_title}")
    lines.append("\n```toc")
    for spec in chapters:
        lines.append(f"{spec.part_no}|{spec.part_title}|{spec.chapter_no}|{spec.chapter_title}")
    lines.append("```\n")
    return "\n".join(lines)


def migrate(source_dir: Path, build_module_name: str, target_slug: str) -> Path:
    module = _load_build_module(source_dir, build_module_name)
    ordered_files: list[Path] = getattr(module, "ORDERED_FILES")
    mermaid_injections: dict = getattr(module, "MERMAID_INJECTIONS", {})

    chapter_pairs = collect_chapters(ordered_files)
    print(f"📚 마이그레이션 대상 챕터: {len(chapter_pairs)}개")

    project_dir = ensure_project_dir(target_slug)

    copied_part_dirs: set[Path] = set()
    matched_injection_keys: set[str] = set()

    for spec, src_path in chapter_pairs:
        dest_dir = project_dir / spec.part_dir_name
        dest_path = dest_dir / spec.chapter_file_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        content = src_path.read_text(encoding="utf-8")

        # MERMAID_INJECTIONS 인라인화 — 원본 stem이 키와 일치하면 앵커 헤딩 뒤에 삽입.
        # 값 문자열 자체에 @@HTML_START@@/@@HTML_END@@가 이미 포함돼 있어 그대로 붙여넣으면
        # html_builder.md_to_html()이 표준 markdown 파서를 우회해 그대로 렌더한다.
        injections = mermaid_injections.get(src_path.stem, [])
        for anchor, injected in injections:
            if anchor in content:
                content = content.replace(anchor, f"{anchor}\n\n{injected}\n", 1)
                matched_injection_keys.add(src_path.stem)

        dest_path.write_text(content, encoding="utf-8")

        src_images = src_path.parent / "images"
        if src_images.is_dir() and src_path.parent not in copied_part_dirs:
            dest_images = dest_dir / "images"
            dest_images.mkdir(exist_ok=True)
            for img in src_images.iterdir():
                shutil.copy2(img, dest_images / img.name)
            copied_part_dirs.add(src_path.parent)

        print(f"  copied: {src_path.relative_to(source_dir)} → {dest_path.relative_to(project_dir)}")

    toc_md = build_toc_manifest([spec for spec, _ in chapter_pairs])
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")

    preface = source_dir / "00_서문.md"
    if preface.is_file():
        shutil.copy2(preface, project_dir / "00_서문.md")
        print(f"  copied (참고용, 목차 미포함): {preface.name}")

    skipped_keys = set(mermaid_injections.keys()) - matched_injection_keys
    if skipped_keys:
        print(
            f"\n⚠️  자동 반영되지 않은 MERMAID_INJECTIONS 키 "
            f"(챕터가 아니거나 앵커 텍스트 불일치): {sorted(skipped_keys)}"
        )
        print("   수동으로 확인 후 필요하면 해당 .md에 직접 @@HTML_START@@ 블록을 추가하세요.")

    print(f"\n✅ 마이그레이션 완료: {project_dir}")
    print(f"   목차: {project_dir / '01_목차.md'}")
    print(f"   다음: book-forge build html {target_slug}")
    return project_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", required=True, type=Path, help="Book/AOO 소스 디렉토리")
    parser.add_argument("--build-module", required=True, help="build_book | build_aoo_book (확장자 제외)")
    parser.add_argument("--target-slug", required=True, help="새 Book-forge 프로젝트 슬러그")
    args = parser.parse_args()
    migrate(args.source.resolve(), args.build_module, args.target_slug)


if __name__ == "__main__":
    main()
