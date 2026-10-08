import pytest

from sat_sim.app import greeting, main


def test_greeting_uses_default_name() -> None:
    assert greeting() == "Hello from sat-sim!"


def test_greeting_accepts_a_custom_name() -> None:
    assert greeting("Python") == "Hello from Python!"


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    assert capsys.readouterr().out == "Hello from sat-sim!\n"
