"""Simple numeric product limits (spec section 6) that don't fit naturally
under quota.py or dataset_validation.py."""

from __future__ import annotations

from common.domain.dataset_validation import ValidationResult

MAX_TRAINING_STEPS = 20_000
MIN_TRAINING_STEPS = 1


def validate_training_steps(steps: int) -> ValidationResult:
    if steps < MIN_TRAINING_STEPS:
        return ValidationResult.failure("Training steps must be a positive integer")
    if steps > MAX_TRAINING_STEPS:
        return ValidationResult.failure(f"Training steps exceeds the maximum of {MAX_TRAINING_STEPS}")
    return ValidationResult.success()
