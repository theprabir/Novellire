"""Installation preflight: every check, with no network and no model."""

from __future__ import annotations

import json

import pytest

from novellire.__main__ import main
from novellire.config import CloudSettings, Settings
from novellire.core.preflight import (
    FAIL,
    OK,
    WARN,
    format_report,
    run_preflight,
)
from novellire.storage.database import Database, utc_now_iso
from novellire.storage.schema import LATEST_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def _clear_cloud_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NOVELLIRE_CONFIG",
        "NOVELLIRE_DATA_DIR",
        "NOVELLIRE_CLOUD_ENABLED",
        "NOVELLIRE_CLOUD_URL",
        "NOVELLIRE_CLOUD_MODEL",
        "NOVELLIRE_CLOUD_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _settings(tmp_path, **overrides) -> Settings:
    return Settings(data_dir=tmp_path / "library", **overrides)


def _check(report, name: str):
    return next(check for check in report.checks if check.name == name)


def _seed_project(database: Database, name: str = "Benchmark") -> None:
    now = utc_now_iso()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO projects (name, created_at, updated_at) VALUES (?, ?, ?)",
            (name, now, now),
        )


def test_fresh_install_is_ready_and_creates_nothing(tmp_path):
    settings = _settings(tmp_path)

    report = run_preflight(settings, tmp_path / "absent.toml")

    assert report.ok is True
    assert report.failures == ()
    assert _check(report, "python").status == OK
    assert _check(report, "data directory").status == OK
    database_check = _check(report, "database")
    assert database_check.status == OK
    assert str(LATEST_SCHEMA_VERSION) in database_check.detail
    # A preflight must not create the directory or the database it inspects.
    assert not settings.data_dir.exists()
    assert not settings.database_path.exists()


def test_existing_database_reports_schema_and_counts(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    database = Database(settings.database_path)
    database.initialize()
    _seed_project(database)
    _seed_project(database, "Second")

    report = run_preflight(settings)

    database_check = _check(report, "database")
    assert database_check.status == OK
    assert f"schema {LATEST_SCHEMA_VERSION} is current" in database_check.detail
    assert "2 projects, 0 chapters" in database_check.detail
    assert report.ok is True


def test_pending_upgrade_is_a_warning_not_a_failure(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    database = Database(settings.database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version > 5")

    report = run_preflight(settings)

    database_check = _check(report, "database")
    assert database_check.status == WARN
    assert "upgrade to" in database_check.detail
    assert database_check.hint
    assert report.ok is True


def test_newer_schema_is_reported_as_a_warning(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    database = Database(settings.database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (LATEST_SCHEMA_VERSION + 1, utc_now_iso()),
        )

    report = run_preflight(settings)

    database_check = _check(report, "database")
    assert database_check.status == WARN
    assert "newer than this install" in database_check.detail


def test_unreadable_database_fails_with_a_recovery_hint(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    settings.database_path.write_bytes(b"this is not a database")

    report = run_preflight(settings)

    database_check = _check(report, "database")
    assert database_check.status == FAIL
    assert "backup" in database_check.hint.lower()
    assert report.ok is False
    # The file is left exactly as it was found.
    assert settings.database_path.read_bytes() == b"this is not a database"


def test_data_directory_that_is_a_file_fails(tmp_path):
    blocker = tmp_path / "library"
    blocker.write_text("a file, not a directory", encoding="utf-8")

    report = run_preflight(Settings(data_dir=blocker))

    directory_check = _check(report, "data directory")
    assert directory_check.status == FAIL
    assert directory_check.hint
    assert report.ok is False


def test_cloud_without_a_key_fails_and_never_prints_a_key(tmp_path):
    settings = _settings(tmp_path, cloud=CloudSettings(enabled=True))

    report = run_preflight(settings)

    provider_check = _check(report, "provider")
    assert provider_check.status == FAIL
    assert "NOVELLIRE_CLOUD_API_KEY" in provider_check.detail
    assert "cloud.enabled = false" in provider_check.hint
    assert report.ok is False


def test_cloud_with_a_key_passes_without_exposing_it(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVELLIRE_CLOUD_API_KEY", "sk-doctor-secret")
    settings = _settings(
        tmp_path,
        cloud=CloudSettings(enabled=True, model="doctor-model"),
    )

    report = run_preflight(settings)

    provider_check = _check(report, "provider")
    assert provider_check.status == OK
    assert "doctor-model" in provider_check.detail
    assert "NOVELLIRE_CLOUD_API_KEY" in provider_check.detail
    assert "sk-doctor-secret" not in json.dumps(report.as_dict())
    assert "sk-doctor-secret" not in format_report(report)


def test_doctor_cli_reports_json_and_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NOVELLIRE_DATA_DIR", str(tmp_path / "library"))

    exit_code = main(["doctor", "--json", "--config", str(tmp_path / "absent.toml")])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "python",
        "configuration",
        "data directory",
        "database",
        "provider",
    ]


def test_doctor_cli_exits_one_when_a_check_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NOVELLIRE_DATA_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("NOVELLIRE_CLOUD_ENABLED", "true")

    exit_code = main(["doctor", "--config", str(tmp_path / "absent.toml")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "1 check failed" in captured.out
    assert "NOVELLIRE_CLOUD_API_KEY" in captured.out


def test_doctor_cli_reports_a_broken_configuration(tmp_path, capsys):
    broken = tmp_path / "config.toml"
    broken.write_text("this is not = valid toml", encoding="utf-8")

    exit_code = main(["doctor", "--config", str(broken)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert str(broken) in captured.err
    assert captured.out == ""
