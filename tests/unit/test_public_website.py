# ruff: noqa: I001, RUF001

from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]


def test_public_website_has_company_product_and_separate_application_entry() -> None:
    html = (REPOSITORY / "website" / "index.html").read_text(encoding="utf-8")
    assert "ООО «АСД-КОНТУР»" in html
    assert "доказательный программный комплекс" in html.casefold()
    assert html.count('href="https://app.asd-kontur.ru"') >= 3
    assert "Войти в АСД-КОНТУР" in html
    for mode in ("Tender", "Support", "Audit", "Restoration"):
        assert f"<h3>{mode}</h3>" in html


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
