"""Confirm the mercury dependency resolves and the public invoke entrypoint imports."""

from mercury.invoke import invoke_mercury


def test_mercury_invoke_entrypoint_importable() -> None:
    assert callable(invoke_mercury)
