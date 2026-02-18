"""Error recovery — pattern detection, retry strategies, exponential backoff."""

import asyncio
import copy
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    CUDA_OOM = "cuda_out_of_memory"
    TIMEOUT = "timeout"
    MODEL_MISSING = "model_missing"
    NETWORK_ERROR = "network_error"
    DISK_FULL = "disk_full"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    RETRY = "retry"
    REDUCE_PARAMS = "reduce_parameters"
    SWITCH_MODEL = "switch_model"
    ABORT = "abort"


@dataclass
class ErrorPattern:
    error_type: ErrorType
    patterns: list[str]
    strategy: RecoveryStrategy
    param_adjustments: dict[str, Any]
    max_retries: int = 3


# Default error patterns for ComfyUI/generation tasks
ERROR_PATTERNS = [
    ErrorPattern(
        error_type=ErrorType.CUDA_OOM,
        patterns=["CUDA out of memory", "OutOfMemoryError", "RuntimeError.*out of memory",
                  "insufficient memory", "GPU memory"],
        strategy=RecoveryStrategy.REDUCE_PARAMS,
        param_adjustments={
            "width": {"operation": "reduce", "factor": 0.8, "min_value": 512},
            "height": {"operation": "reduce", "factor": 0.8, "min_value": 512},
            "steps": {"operation": "reduce", "factor": 0.8, "min_value": 20},
        },
        max_retries=3,
    ),
    ErrorPattern(
        error_type=ErrorType.TIMEOUT,
        patterns=["TimeoutError", "Request timeout", "Connection timeout", "Read timeout"],
        strategy=RecoveryStrategy.RETRY,
        param_adjustments={},
        max_retries=2,
    ),
    ErrorPattern(
        error_type=ErrorType.MODEL_MISSING,
        patterns=["Model not found", "FileNotFoundError.*models", "No such file.*checkpoint"],
        strategy=RecoveryStrategy.ABORT,
        param_adjustments={},
        max_retries=0,
    ),
    ErrorPattern(
        error_type=ErrorType.NETWORK_ERROR,
        patterns=["ConnectionError", "Network unreachable", "Connection refused", "HTTP.*50[0-9]"],
        strategy=RecoveryStrategy.RETRY,
        param_adjustments={},
        max_retries=3,
    ),
    ErrorPattern(
        error_type=ErrorType.DISK_FULL,
        patterns=["No space left on device", "Disk full", "OSError.*28"],
        strategy=RecoveryStrategy.ABORT,
        param_adjustments={},
        max_retries=0,
    ),
]


def classify_error(error_message: str) -> tuple[ErrorType, ErrorPattern]:
    """Classify error and return appropriate recovery pattern."""
    for pattern in ERROR_PATTERNS:
        for regex in pattern.patterns:
            if re.search(regex, error_message, re.IGNORECASE):
                logger.info(f"Classified error as {pattern.error_type.value}: {error_message[:100]}")
                return pattern.error_type, pattern
    default = ErrorPattern(
        error_type=ErrorType.UNKNOWN, patterns=[], strategy=RecoveryStrategy.RETRY,
        param_adjustments={}, max_retries=1,
    )
    return ErrorType.UNKNOWN, default


def adjust_parameters(original_params: dict, adjustments: dict) -> dict:
    """Apply parameter adjustments based on error pattern."""
    adjusted = copy.deepcopy(original_params)
    for param_name, adj in adjustments.items():
        if param_name not in adjusted:
            continue
        current = adjusted[param_name]
        op = adj.get("operation")
        if op == "reduce":
            factor = adj.get("factor", 0.8)
            min_val = adj.get("min_value", 1)
            adjusted[param_name] = max(int(current * factor), min_val)
            logger.info(f"Reduced {param_name}: {current} → {adjusted[param_name]}")
        elif op == "divide":
            factor = adj.get("factor", 2)
            min_val = adj.get("min_value", 1)
            adjusted[param_name] = max(int(current / factor), min_val)
            logger.info(f"Divided {param_name}: {current} → {adjusted[param_name]}")
    return adjusted


async def attempt_recovery(
    error_message: str,
    original_params: dict,
    attempt_number: int = 1,
) -> tuple[bool, dict, str]:
    """Attempt recovery from an error. Returns (success, new_params, message)."""
    error_type, pattern = classify_error(error_message)

    if attempt_number > pattern.max_retries:
        return False, original_params, f"Max retries ({pattern.max_retries}) exceeded for {error_type.value}"

    if pattern.strategy == RecoveryStrategy.ABORT:
        return False, original_params, f"Unrecoverable error: {error_type.value}"

    if pattern.strategy == RecoveryStrategy.REDUCE_PARAMS:
        new_params = adjust_parameters(original_params, pattern.param_adjustments)
        return True, new_params, f"Reduced parameters for {error_type.value} (attempt {attempt_number})"

    if pattern.strategy == RecoveryStrategy.RETRY:
        backoff = min(2 ** attempt_number, 30)
        await asyncio.sleep(backoff)
        return True, original_params, f"Retrying after {backoff}s (attempt {attempt_number})"

    return False, original_params, f"No recovery strategy for {error_type.value}"
