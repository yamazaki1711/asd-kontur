from io import BytesIO

from PIL import Image

from asd_kontur.ntd.canonical_memory import _is_deterministic_blank_png


def _png(pixels: list[int]) -> bytes:
    image = Image.new("L", (10, 10))
    image.putdata(pixels)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_white_and_near_white_renders_are_blank() -> None:
    assert _is_deterministic_blank_png(_png([255] * 100))
    assert _is_deterministic_blank_png(_png([255] * 99 + [250]))


def test_high_variance_or_dark_renders_are_not_blank() -> None:
    assert not _is_deterministic_blank_png(_png([0] * 50 + [255] * 50))
    assert not _is_deterministic_blank_png(_png([100] * 99 + [255]))


def test_invalid_png_is_not_blank() -> None:
    assert not _is_deterministic_blank_png(b"not-a-png")
