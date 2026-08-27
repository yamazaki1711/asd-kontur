from __future__ import annotations

from asd_kontur.ntd.file_processing import extract_critical_tokens


def test_critical_tokens_preserve_normative_values_and_modal_words() -> None:
    text = (
        "7.1.13 Результаты не допускается округлять: отклонение ± 5 мм, "
        "площадь 12,5 м², объем 3.25 м³; оператор должен сохранить 100 %."
    )

    assert extract_critical_tokens(text) == (
        "7.1.13",
        "не допускается",
        "±",
        "5",
        "мм",
        "12,5",
        "м²",
        "3.25",
        "м³",
        "должен",
        "100",
        "%",
    )


def test_critical_tokens_do_not_invent_units_inside_russian_words() -> None:
    assert (
        extract_critical_tokens("строительство документируется материалами и результатами контроля")
        == ()
    )
