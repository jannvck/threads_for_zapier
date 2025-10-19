from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import Settings


def test_settings_reads_file_based_configuration(monkeypatch, tmp_path):
    secret_file = tmp_path / "client_secret.txt"
    secret_file.write_text("super-secret\n", encoding="utf-8")

    monkeypatch.delenv("THREADS_ZAPIER_THREADS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("THREADS_ZAPIER_THREADS_CLIENT_SECRET_FILE", str(secret_file))

    settings = Settings()

    assert settings.threads_client_secret == "super-secret"
