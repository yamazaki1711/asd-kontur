"""Check every rendered contract-document page without emitting its content.

This is a layout diagnostic, not a legal or semantic correctness decision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {"x": "http://www.w3.org/1999/xhtml"}


def inspect_pdf(path: Path) -> dict[str, object]:
    result = subprocess.run(
        ["pdftotext", "-bbox-layout", str(path), "-"],
        check=True,
        capture_output=True,
    )
    document = ET.fromstring(result.stdout)
    pages = document.findall(".//x:page", _NS)
    if not pages:
        raise ValueError("rendered_pdf_has_no_pages")
    word_counts: list[int] = []
    empty_pages: list[int] = []
    clipped_pages: list[int] = []
    edge_pages: list[int] = []
    for number, page in enumerate(pages, start=1):
        width = float(page.attrib["width"])
        height = float(page.attrib["height"])
        words = page.findall(".//x:word", _NS)
        word_counts.append(len(words))
        if not words:
            empty_pages.append(number)
        for word in words:
            x0, y0, x1, y1 = (float(word.attrib[key]) for key in ("xMin", "yMin", "xMax", "yMax"))
            if x0 < -0.1 or y0 < -0.1 or x1 > width + 0.1 or y1 > height + 0.1:
                clipped_pages.append(number)
            elif x0 < 6 or y0 < 6 or x1 > width - 6 or y1 > height - 6:
                edge_pages.append(number)
    return {
        "file": path.name,
        "pages": len(pages),
        "empty_pages": sorted(set(empty_pages)),
        "out_of_page_text_pages": sorted(set(clipped_pages)),
        "within_six_points_of_edge_pages": sorted(set(edge_pages)),
        "minimum_words_on_page": min(word_counts),
        "maximum_words_on_page": max(word_counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([inspect_pdf(path) for path in args.pdf], sort_keys=True))


if __name__ == "__main__":
    main()
