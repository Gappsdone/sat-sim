from sat_sim.app import greeting


def test_greeting_uses_default_name() -> None:
    assert greeting() == "Hello from sat-sim!"


def test_greeting_accepts_a_custom_name() -> None:
    assert greeting("Python") == "Hello from Python!"
