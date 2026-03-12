#!/usr/bin/env python3

import argparse
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        sys.exit(
            "Error: PyMuPDF is not installed. Install it with: sudo dnf install python3-PyMuPDF"
        )

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def build_font_xrefs(page: Any) -> dict[str, int]:
    """Maps clean font names to their internal xrefs for extraction."""
    xrefs: dict[str, int] = {}
    for f in page.get_fonts():
        xref = f[0]
        base_name = f[3]
        clean_name = base_name.split("+")[-1].lower()
        xrefs[clean_name] = xref
    return xrefs


def iter_text_spans(blocks: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yields text spans from PyMuPDF text blocks."""
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                yield span


def process_pdf(
    input_path: Path,
    target_path: Path,
    replacements_list: list[tuple[str, str]],
) -> None:
    """Processes the PDF to find and replace text."""
    try:
        doc = pymupdf.open(input_path)
    except Exception as e:
        logger.error(f"Failed to open input PDF '{input_path}': {e}")
        sys.exit(1)

    total_replacements = 0

    for page in doc:
        font_xrefs = build_font_xrefs(page)
        blocks = (
            page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT).get("blocks", [])
        )

        insertions: list[tuple[Any, str, str, float, bytes | None]] = []
        page_replacements = 0

        for search_str, replace_str in replacements_list:
            rects = page.search_for(search_str)
            if not rects:
                continue

            for r in rects:
                origin_y = r.y1 - 1.5
                font_name = "helv"
                font_size = 11.0
                font_buffer: bytes | None = None

                # Pick the first intersecting span (don’t let later spans override it).
                for span in iter_text_spans(blocks):
                    if not pymupdf.Rect(span["bbox"]).intersects(r):
                        continue

                    origin_y = span["origin"][1]
                    font_size = float(span["size"])
                    clean_font = span["font"].split("+")[-1].lower()

                    xref = font_xrefs.get(clean_font)
                    if xref:
                        try:
                            extracted = doc.extract_font(xref)
                            font_buffer = extracted[3] if extracted[3] else None
                            font_name = clean_font if font_buffer else "helv"
                        except Exception as e:
                            logger.debug(f"Failed to extract font xref {xref}: {e}")

                    break

                insertion_point = pymupdf.Point(r.x0, origin_y)
                insertions.append(
                    (insertion_point, replace_str, font_name, font_size, font_buffer)
                )

                page.add_redact_annot(r)
                page_replacements += 1
                total_replacements += 1

        if page_replacements > 0:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

            registered_fonts: set[str] = set()
            for (pt, repl, font_name, font_size, font_buffer) in insertions:
                if font_buffer and font_name not in registered_fonts:
                    page.insert_font(fontname=font_name, fontbuffer=font_buffer)
                    registered_fonts.add(font_name)

                page.insert_text(pt, repl, fontname=font_name, fontsize=font_size)

    if total_replacements == 0:
        logger.info("No matches found. No changes made to the file.")
        doc.close()
        return

    temp_dir = target_path.parent
    if not temp_dir.exists():
        logger.error(f"Target directory does not exist: {temp_dir}")
        doc.close()
        sys.exit(1)

    # Create temp path in same directory for atomic replace, without fd leaks.
    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=".pdf", delete=False) as tf:
        temp_path = Path(tf.name)

    try:
        doc.save(temp_path, garbage=4, deflate=True)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        logger.error(f"Failed to save PDF: {e}")
        sys.exit(1)
    finally:
        doc.close()

    try:
        temp_path.replace(target_path)
        logger.info(
            f"Success! Replaced {total_replacements} occurrence(s). Saved to '{target_path}'."
        )
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        logger.error(f"Failed to overwrite target file '{target_path}': {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find and replace multiple strings in a PDF while preserving exact baseline positions."
    )

    parser.add_argument("input", type=Path, help="Path to the source PDF file")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-o", "--output", type=Path, help="Path to save the modified PDF file")
    group.add_argument("-i", "--in-place", action="store_true", help="Modify the input file in-place")

    parser.add_argument(
        "-e",
        "--expression",
        nargs=2,
        action="append",
        metavar=("SEARCH", "REPLACE"),
        required=True,
        help="Search and replace strings. Use multiple times for multiple pairs.",
    )

    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing files without prompting",
    )

    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.exists() or not input_path.is_file():
        logger.error(f"Input file not found or is not a file: {input_path}")
        sys.exit(1)

    target_path: Path = input_path if args.in_place else args.output

    if target_path.exists() and not args.force:
        response = input(f"File '{target_path}' already exists. Overwrite? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            logger.info("Operation cancelled by user.")
            sys.exit(0)

    process_pdf(input_path, target_path, args.expression)


if __name__ == "__main__":
    main()
