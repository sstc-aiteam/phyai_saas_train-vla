"""Policy input compatibility checks (spec step 3c).

Reads the `features` map from a dataset's `meta/info.json` (LeRobot v3
metadata format) and checks it against the minimal input contract each
supported policy needs. This is deliberately a simplified stub of the real
LeRobot policy config shape-matching logic — good enough to reject obviously
incompatible datasets without depending on the (unavailable in this
environment) `lerobot` package itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from common.domain.dataset_validation import ValidationResult
from common.models import PolicyType


@dataclass(frozen=True)
class PolicyRequirement:
    required_features: tuple[str, ...]
    requires_visual_feature: bool


POLICY_REQUIREMENTS: dict[PolicyType, PolicyRequirement] = {
    PolicyType.ACT: PolicyRequirement(
        required_features=("observation.state", "action"),
        requires_visual_feature=False,
    ),
    PolicyType.SMOLVLA: PolicyRequirement(
        required_features=("observation.state", "action"),
        requires_visual_feature=True,
    ),
}

_VISUAL_FEATURE_PREFIXES = ("observation.image", "observation.images")


class InvalidInfoJsonError(Exception):
    pass


def parse_info_json(raw: bytes) -> dict:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidInfoJsonError(f"meta/info.json is not valid JSON: {exc}") from exc


def check_policy_compatibility(info: dict, policy: PolicyType) -> ValidationResult:
    requirement = POLICY_REQUIREMENTS[policy]
    features = info.get("features", {})
    if not isinstance(features, dict):
        return ValidationResult.failure("meta/info.json is missing a valid 'features' map")

    for feature_name in requirement.required_features:
        if feature_name not in features:
            return ValidationResult.failure(
                f"Dataset is missing feature '{feature_name}' required by policy '{policy.value}'"
            )

    if requirement.requires_visual_feature:
        has_visual = any(
            feature_name.startswith(prefix)
            for feature_name in features
            for prefix in _VISUAL_FEATURE_PREFIXES
        )
        if not has_visual:
            return ValidationResult.failure(
                f"Policy '{policy.value}' requires at least one visual observation feature"
            )

    return ValidationResult.success()
