# ruff: noqa: RUF001 - Russian construction terms are intentional corpus content.

"""Build the deterministic, anonymized intake qualification corpus outside Git."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

CORPUS_VERSION = "industrial-intake-synthetic@1.0.0"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _zip_entry(name: str, content: str | bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100600 << 16
    return info, content.encode("utf-8") if isinstance(content, str) else content


def _write_zip(path: Path, entries: list[tuple[str, str | bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries:
            info, payload = _zip_entry(name, content)
            archive.writestr(info, payload)


def _docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(f"<w:p><w:r><w:t>{escape(value)}</w:t></w:r></w:p>" for value in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    _write_zip(
        path,
        [
            ("[Content_Types].xml", "<Types/>"),
            ("word/document.xml", document),
        ],
    )


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xlsx(path: Path, rows: list[list[str]]) -> None:
    cells: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        values = "".join(
            f'<c r="{_column(column_index)}{row_index}" t="inlineStr">'
            f"<is><t>{escape(value)}</t></is></c>"
            for column_index, value in enumerate(row, start=1)
        )
        cells.append(f'<row r="{row_index}">{values}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(cells)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Лист1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    _write_zip(
        path,
        [
            ("[Content_Types].xml", "<Types/>"),
            ("xl/workbook.xml", workbook),
            ("xl/_rels/workbook.xml.rels", relationships),
            ("xl/worksheets/sheet1.xml", sheet),
        ],
    )


def _font() -> str:
    for path in (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if path.is_file():
            pdfmetrics.registerFont(TTFont("CorpusSans", path))
            return "CorpusSans"
    return "Helvetica"


def _native_pdf(path: Path, lines: list[str]) -> None:
    target = canvas.Canvas(str(path), pagesize=A4, invariant=1, pageCompression=0)
    target.setFont(_font(), 11)
    y = A4[1] - 64
    for line in lines:
        target.drawString(56, y, line)
        y -= 20
    target.showPage()
    target.save()


def _mixed_pdf(path: Path) -> None:
    image = Image.new("RGB", (1240, 1754), "white")
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((80, 80, 1160, 1670), outline="black", width=4)
    drawing.text((120, 140), "RASTER PAGE / RD-02", fill="black")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG", optimize=False)
    image_bytes.seek(0)
    target = canvas.Canvas(str(path), pagesize=A4, invariant=1, pageCompression=0)
    target.setFont(_font(), 11)
    target.drawString(56, A4[1] - 64, "Рабочая документация")
    target.drawString(56, A4[1] - 84, "Комплект рабочих чертежей РД-01")
    target.showPage()
    target.drawImage(ImageReader(image_bytes), 0, 0, width=A4[0], height=A4[1])
    target.showPage()
    target.save()


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


def build(root: Path) -> dict[str, object]:
    if root.exists() and any(root.iterdir()):
        raise ValueError("target directory must be empty")
    root.mkdir(parents=True, exist_ok=True)
    (root / "01_Проект").mkdir()
    (root / "02_Договор").mkdir()
    (root / "03_Объемы_и_смета").mkdir()
    (root / "04_Материалы").mkdir()
    (root / "05_Проверка_приема").mkdir()

    _docx(
        root / "01_Проект" / "Пояснительная_записка.docx",
        [
            "Пояснительная записка",
            "Наименование объекта: Учебно-производственный корпус",
            "Назначение объекта: Подготовка строительных специалистов",
            "Состав объекта: Главный корпус; наружная сеть водоснабжения",
            "Части объекта: Главный корпус; наружная сеть",
            "Зоны работ: Зона А; Зона Б",
            "Уровни: 0,000; +4,200",
            "Фронты работ: Фронт Ф1; Фронт Ф2",
            "Зависимости работ: Монолитная плита до гидроизоляции; сеть после земляных работ",
        ],
    )
    _native_pdf(
        root / "01_Проект" / "Раздел_ПД.pdf",
        ["Проектная документация", "Раздел проектной документации", "Проектные решения"],
    )
    _mixed_pdf(root / "01_Проект" / "Рабочая_документация_смешанная.pdf")
    _docx(
        root / "02_Договор" / "Договор.docx",
        [
            "Договор строительного подряда",
            "Предмет договора: выполнение строительно-монтажных работ",
        ],
    )
    _native_pdf(
        root / "02_Договор" / "Требования_заказчика.pdf",
        [
            "Регламент заказчика",
            "Требования заказчика",
            "Предъявление работ по завершении контроля",
        ],
    )
    _xlsx(
        root / "03_Объемы_и_смета" / "Ведомость_объемов.xlsx",
        [
            ["Ведомость объёмов работ"],
            [
                "Вид работ",
                "Объём",
                "Ед. изм.",
                "Материал",
                "Количество материала",
                "Ед. изм. материала",
            ],
            ["Устройство монолитной плиты", "12,350", "м³", "Бетон В25", "12,350", "м³"],
            ["Устройство гидроизоляции", "840", "м²", "Мембрана", "900", "м²"],
            ["Монтаж трубопровода", "145", "м", "Труба 159х6", "145", "м"],
        ],
    )
    _xlsx(
        root / "03_Объемы_и_смета" / "Локальная_смета.xlsx",
        [
            ["Локальная смета"],
            ["Позиция", "Вид работ", "Объём", "Ед. изм."],
            ["01-01", "Устройство монолитной плиты", "12,000", "м³"],
            ["01-02", "Монтаж трубопровода", "145", "м"],
        ],
    )
    _xlsx(
        root / "04_Материалы" / "Спецификация_материалов.xlsx",
        [
            ["Спецификация материалов"],
            ["Материал", "Количество", "Единица"],
            ["Бетон В25", "12,350", "м³"],
            ["Мембрана", "900", "м²"],
            ["Труба 159х6", "145", "м"],
        ],
    )
    source_pdf = root / "01_Проект" / "Раздел_ПД.pdf"
    shutil.copyfile(source_pdf, root / "05_Проверка_приема" / "Раздел_ПД_копия.pdf")
    shutil.copyfile(source_pdf, root / "05_Проверка_приема" / "Файл_с_неверным_расширением.txt")
    (root / "05_Проверка_приема" / "Неподдерживаемая_модель.ifc").write_bytes(
        b"ISO-10303-21;\x00\x01 synthetic unsupported IFC"
    )
    (root / "05_Проверка_приема" / "Поврежденный_документ.pdf").write_bytes(
        b"%PDF-1.7\ntruncated synthetic document"
    )
    _write_zip(
        root / "05_Проверка_приема" / "Дополнительный_комплект.zip",
        [
            ("ТЗ/техническое_задание.txt", "Техническое задание: устройство учебного корпуса"),
            ("Журналы/перечень.csv", "Документ;Состояние\nОбщий журнал работ;отсутствует\n"),
        ],
    )

    files = sorted(path for path in root.rglob("*") if path.is_file())
    manifest: dict[str, object] = {
        "corpus_version": CORPUS_VERSION,
        "synthetic": True,
        "contains_real_oks_data": False,
        "files": [
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _digest(path),
            }
            for path in files
        ],
        "control_denominator": {
            "object_parts": 2,
            "zones": 2,
            "levels": 2,
            "work_fronts": 2,
            "work_types": 3,
            "quantities": 3,
            "materials": 3,
            "dependencies": 2,
            "vor_estimate_mismatches": 2,
            "known_missing": ["confirmed_geometry", "material_quality_documents"],
            "expected_intake_outcomes": {
                "unsupported": 1,
                "quarantined": 1,
                "archive_members": 2,
                "same_bytes_candidates": 3,
            },
        },
    }
    manifest["logical_fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    (root / "corpus-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    manifest = build(args.target.resolve())
    print(manifest["logical_fingerprint"])


if __name__ == "__main__":
    main()
