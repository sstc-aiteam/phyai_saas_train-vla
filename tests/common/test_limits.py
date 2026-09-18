from common.domain.limits import MAX_TRAINING_STEPS, validate_training_steps


def test_valid_steps_pass():
    assert validate_training_steps(1000).ok is True


def test_zero_steps_fail():
    assert validate_training_steps(0).ok is False


def test_negative_steps_fail():
    assert validate_training_steps(-5).ok is False


def test_steps_at_max_pass():
    assert validate_training_steps(MAX_TRAINING_STEPS).ok is True


def test_steps_over_max_fail():
    result = validate_training_steps(MAX_TRAINING_STEPS + 1)
    assert result.ok is False
    assert "maximum" in result.error
