"""The password the smoke packs and the BDD suite sign in with: `SMOKE_PASSWORD` when a
preview has its own (handoff 09, decision 11), else the k3d and Compose values' `collabhub`."""

from __future__ import annotations

import importlib

import pytest


def default_password(monkeypatch: pytest.MonkeyPatch, value: str | None) -> str:
    if value is None:
        monkeypatch.delenv("SMOKE_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SMOKE_PASSWORD", value)
    module = importlib.reload(importlib.import_module("bdd.pages.sign_in_page"))
    return module.SignInPage.sign_in.__defaults__[0]


def test_the_default_is_the_shared_dev_password(monkeypatch: pytest.MonkeyPatch) -> None:
    assert default_password(monkeypatch, None) == "collabhub"


def test_an_empty_smoke_password_is_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    assert default_password(monkeypatch, "") == "collabhub"


def test_a_previews_own_password_is_signed_in_with(monkeypatch: pytest.MonkeyPatch) -> None:
    assert default_password(monkeypatch, "s3cret-Pw") == "s3cret-Pw"
