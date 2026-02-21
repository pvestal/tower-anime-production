"""Unit tests for packages.core.errors — error classification and recovery."""

import pytest

from packages.core.errors import (
    ErrorType,
    RecoveryStrategy,
    adjust_parameters,
    attempt_recovery,
    classify_error,
)


# ---------------------------------------------------------------------------
# classify_error
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_classify_cuda_oom():
    """CUDA OOM message classified as CUDA_OOM with REDUCE_PARAMS strategy."""
    error_type, pattern = classify_error("CUDA out of memory")
    assert error_type == ErrorType.CUDA_OOM
    assert pattern.strategy == RecoveryStrategy.REDUCE_PARAMS


@pytest.mark.unit
def test_classify_timeout():
    """Timeout message classified as TIMEOUT."""
    error_type, pattern = classify_error("TimeoutError")
    assert error_type == ErrorType.TIMEOUT
    assert pattern.strategy == RecoveryStrategy.RETRY


@pytest.mark.unit
def test_classify_model_missing():
    """Model not found classified as MODEL_MISSING with ABORT strategy."""
    error_type, pattern = classify_error("Model not found")
    assert error_type == ErrorType.MODEL_MISSING
    assert pattern.strategy == RecoveryStrategy.ABORT


@pytest.mark.unit
def test_classify_network_error():
    """Connection refused classified as NETWORK_ERROR."""
    error_type, pattern = classify_error("Connection refused")
    assert error_type == ErrorType.NETWORK_ERROR
    assert pattern.strategy == RecoveryStrategy.RETRY


@pytest.mark.unit
def test_classify_disk_full():
    """Disk full classified as DISK_FULL with ABORT strategy."""
    error_type, pattern = classify_error("No space left on device")
    assert error_type == ErrorType.DISK_FULL
    assert pattern.strategy == RecoveryStrategy.ABORT


@pytest.mark.unit
def test_classify_unknown():
    """Unrecognized message classified as UNKNOWN."""
    error_type, pattern = classify_error("something random and unexpected")
    assert error_type == ErrorType.UNKNOWN
    assert pattern.strategy == RecoveryStrategy.RETRY


# ---------------------------------------------------------------------------
# adjust_parameters
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_adjust_parameters_reduces_values():
    """adjust_parameters with OOM adjustments reduces width/height/steps."""
    params = {"width": 1024, "height": 1024, "steps": 40}
    adjustments = {
        "width": {"operation": "reduce", "factor": 0.8, "min_value": 512},
        "height": {"operation": "reduce", "factor": 0.8, "min_value": 512},
        "steps": {"operation": "reduce", "factor": 0.8, "min_value": 20},
    }
    result = adjust_parameters(params, adjustments)
    assert result["width"] == 819   # int(1024 * 0.8) = 819
    assert result["height"] == 819
    assert result["steps"] == 32    # int(40 * 0.8) = 32


@pytest.mark.unit
def test_adjust_parameters_skips_missing_keys():
    """adjust_parameters ignores adjustments for keys absent from the params."""
    params = {"width": 1024}
    adjustments = {
        "width": {"operation": "reduce", "factor": 0.5, "min_value": 256},
        "height": {"operation": "reduce", "factor": 0.5, "min_value": 256},
    }
    result = adjust_parameters(params, adjustments)
    assert result["width"] == 512
    assert "height" not in result


@pytest.mark.unit
def test_adjust_parameters_respects_min_value():
    """adjust_parameters clamps to min_value when reduction goes below it."""
    params = {"steps": 10}
    adjustments = {
        "steps": {"operation": "reduce", "factor": 0.1, "min_value": 20},
    }
    result = adjust_parameters(params, adjustments)
    assert result["steps"] == 20  # max(int(10*0.1), 20) = max(1, 20) = 20


@pytest.mark.unit
def test_adjust_parameters_does_not_mutate_original():
    """adjust_parameters returns a new dict; original is unchanged."""
    params = {"width": 1024}
    adjustments = {"width": {"operation": "reduce", "factor": 0.5, "min_value": 256}}
    result = adjust_parameters(params, adjustments)
    assert params["width"] == 1024
    assert result["width"] == 512


# ---------------------------------------------------------------------------
# attempt_recovery (async)
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_attempt_recovery_oom_returns_reduced_params():
    """OOM recovery returns True with reduced parameters."""
    params = {"width": 1024, "height": 1024, "steps": 40}
    success, new_params, msg = await attempt_recovery("CUDA out of memory", params, attempt_number=1)
    assert success is True
    assert new_params["width"] < 1024
    assert "Reduced parameters" in msg


@pytest.mark.unit
async def test_attempt_recovery_abort_returns_false():
    """Unrecoverable errors (ABORT strategy, max_retries=0) return False."""
    params = {"width": 512}
    success, new_params, msg = await attempt_recovery("Model not found in checkpoints", params, attempt_number=1)
    assert success is False
    # MODEL_MISSING has max_retries=0, so attempt 1 exceeds it
    assert "Max retries" in msg or "Unrecoverable" in msg


@pytest.mark.unit
async def test_attempt_recovery_max_retries_exceeded():
    """Exceeding max_retries returns False regardless of strategy."""
    params = {"width": 1024, "height": 1024, "steps": 40}
    # CUDA_OOM has max_retries=3, so attempt 4 should fail
    success, new_params, msg = await attempt_recovery("CUDA out of memory", params, attempt_number=4)
    assert success is False
    assert "Max retries" in msg
