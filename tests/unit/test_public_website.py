# ruff: noqa: I001, RUF001

from pathlib import Path
import re


REPOSITORY = Path(__file__).resolve().parents[2]


def test_public_website_has_company_product_and_separate_application_entry() -> None:
    html = (REPOSITORY / "website" / "index.html").read_text(encoding="utf-8")
    normalized_html = " ".join(html.split())
    assert "ООО «АСД-КОНТУР»" in html
    assert "АСД-КОНТУР — аудит и инженерное сопровождение строительства" in html
    assert (
        "АСД-КОНТУР — программный комплекс для аудита строительной "
        "документации, инженерного сопровождения СМР и формирования "
        "исполнительной документации."
    ) in normalized_html
    assert html.count('href="https://app.asd-kontur.ru"') >= 3
    assert "Войти в комплекс" in html
    for mode in ("Тендер", "Сопровождение", "Аудит", "Восстановление"):
        assert f"<h3>{mode}</h3>" in html


def test_public_website_copy_uses_professional_russian_language() -> None:
    html = (REPOSITORY / "website" / "index.html").read_text(encoding="utf-8")
    visible_copy = " ".join(
        fragment.split("<", 1)[0] for fragment in html.split(">") if "<" in fragment
    )
    for required in (
        "Аудит ПД и РД",
        "Инженерное сопровождение СМР",
        "Комплектность и готовность",
        "Нормативная согласованность",
        "Прослеживаемость",
        "Подтверждённые сведения",
        "Единый контур строительной документации",
    ):
        assert required in html
    for forbidden_token in ("AI", "ИИ"):
        assert (
            re.search(
                rf"(?<![A-Za-zА-Яа-яЁё]){forbidden_token}(?![A-Za-zА-Яа-яЁё])",
                visible_copy,
            )
            is None
        )
    for forbidden in (
        "evidence",
        "Local-first",
        "Tender",
        "Support",
        "Restoration",
        "доказательн",
    ):
        assert forbidden.casefold() not in visible_copy.casefold()


def test_public_website_does_not_leak_legacy_or_pilot_surfaces() -> None:
    html = (REPOSITORY / "website" / "index.html").read_text(encoding="utf-8")
    for forbidden in (
        "ИСУИД",
        "Лева" + "шово",
        "24337",
        "24 337",
        "690 томов",
        "bi.asd-kontur.ru",
        "tm.asd-kontur.ru",
    ):
        assert forbidden not in html


def test_public_website_has_responsive_and_https_only_contract() -> None:
    html = (REPOSITORY / "website" / "index.html").read_text(encoding="utf-8")
    css = (REPOSITORY / "website" / "styles.css").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 600px)" in css
    assert "http://" not in html
