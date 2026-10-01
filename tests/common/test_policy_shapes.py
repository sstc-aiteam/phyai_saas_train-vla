import json

import pytest

from common.domain.policy_shapes import (
    InvalidInfoJsonError,
    check_policy_compatibility,
    parse_info_json,
)
from common.models import PolicyType

STATE_ACTION_ONLY = {
    "features": {
        "observation.state": {"shape": [14]},
        "action": {"shape": [7]},
    }
}

WITH_VISUAL = {
    "features": {
        "observation.state": {"shape": [14]},
        "observation.images.top": {"shape": [3, 224, 224]},
        "action": {"shape": [7]},
    }
}

WITH_ENV_STATE = {
    "features": {
        "observation.state": {"shape": [14]},
        "observation.environment_state": {"shape": [10]},
        "action": {"shape": [7]},
    }
}


def test_act_fails_without_visual_or_env_state_feature():
    # Real lerobot's ACTConfig.validate_features() requires at least one
    # image feature or "observation.environment_state" -- state+action
    # alone isn't enough, even though the service's own required_features
    # list doesn't mention either by name.
    result = check_policy_compatibility(STATE_ACTION_ONLY, PolicyType.ACT)
    assert result.ok is False
    assert "visual" in result.error
    assert "observation.environment_state" in result.error


def test_act_passes_with_visual_feature():
    result = check_policy_compatibility(WITH_VISUAL, PolicyType.ACT)
    assert result.ok is True


def test_act_passes_with_env_state_feature_instead_of_visual():
    result = check_policy_compatibility(WITH_ENV_STATE, PolicyType.ACT)
    assert result.ok is True


def test_act_fails_without_action_feature():
    info = {"features": {"observation.state": {"shape": [14]}, "observation.environment_state": {"shape": [10]}}}
    result = check_policy_compatibility(info, PolicyType.ACT)
    assert result.ok is False
    assert "action" in result.error


def test_smolvla_requires_visual_feature():
    result = check_policy_compatibility(STATE_ACTION_ONLY, PolicyType.SMOLVLA)
    assert result.ok is False
    assert "visual" in result.error


def test_smolvla_passes_with_visual_feature():
    result = check_policy_compatibility(WITH_VISUAL, PolicyType.SMOLVLA)
    assert result.ok is True


def test_missing_features_map_fails():
    result = check_policy_compatibility({}, PolicyType.ACT)
    assert result.ok is False
    assert "observation.state" in result.error


def test_non_dict_features_map_fails():
    result = check_policy_compatibility({"features": "not-a-dict"}, PolicyType.ACT)
    assert result.ok is False
    assert "features" in result.error


def test_parse_info_json_roundtrip():
    raw = json.dumps(STATE_ACTION_ONLY).encode("utf-8")
    assert parse_info_json(raw) == STATE_ACTION_ONLY


def test_parse_info_json_raises_on_invalid_json():
    with pytest.raises(InvalidInfoJsonError):
        parse_info_json(b"not json {{{")
