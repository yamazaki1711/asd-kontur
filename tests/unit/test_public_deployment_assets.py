import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = ROOT / "deployment" / "public"


def test_public_surface_contracts_are_isolated() -> None:
    website = (DEPLOYMENT / "nginx" / "asd-kontur.ru.conf").read_text()
    application = (DEPLOYMENT / "nginx" / "app.asd-kontur.ru.conf").read_text()
    bi = (DEPLOYMENT / "nginx" / "bi.asd-kontur.ru.conf").read_text()

    assert "server_name asd-kontur.ru;" in website
    assert "proxy_pass" not in website
    assert "ИСУИД" not in website
    assert "server_name app.asd-kontur.ru;" in application
    assert "proxy_pass http://172.18.0.1:18766;" in application
    assert "authoritative_primary_unavailable" in application
    assert "server_name bi.asd-kontur.ru;" in bi
    assert "location /levashovo/intake-control/" in bi
    assert "X-Forwarded-Prefix /levashovo/intake-control" in bi
    assert not (DEPLOYMENT / "nginx" / "tm.asd-kontur.ru.conf").exists()


def test_legacy_rollback_configuration_is_exact() -> None:
    archived = DEPLOYMENT / "legacy" / "asd-kontur.ru.pre-cutover-20260827.conf"
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == (
        "bd02f9167ffb29719beffc941122c298adcad7af7142d0bff9d1bc588d56f8e6"
    )


def test_ingress_and_archive_runtime_bindings_are_explicit() -> None:
    socket = (DEPLOYMENT / "systemd" / "asd-kontur-app-ingress.socket").read_text()
    proxy = (DEPLOYMENT / "systemd" / "asd-kontur-app-ingress.service").read_text()
    archive = (DEPLOYMENT / "systemd" / "levashovo-intake-control.service").read_text()

    assert "ListenStream=172.18.0.1:18766" in socket
    assert "127.0.0.1:18765" in proxy
    assert "ISUID_PUBLIC_PREFIX=/levashovo/intake-control" in archive
    assert "--port 8088" in archive
