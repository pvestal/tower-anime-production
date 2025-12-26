"""GPU Management Service"""

import subprocess
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def get_gpu_memory() -> Dict[str, int]:
    """Get GPU memory usage"""
    try:
        result = subprocess.run([
            'nvidia-smi',
            '--query-gpu=memory.free,memory.total',
            '--format=csv,nounits,noheader'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            free, total = map(int, result.stdout.strip().split(','))
            return {'free': free, 'total': total}
    except Exception as e:
        logger.error(f"Error getting GPU memory: {e}")

    return {'free': 0, 'total': 0}


def ensure_vram_available(required_mb: int = 4000) -> bool:
    """Check if enough VRAM is available"""
    memory = get_gpu_memory()
    logger.info(f"Current VRAM: {memory['free']}MB free / {memory['total']}MB total")

    if memory["free"] < required_mb:
        logger.warning(
            f"Insufficient VRAM: {memory['free']}MB < {required_mb}MB required"
        )
        return False
    return True


async def check_gpu_availability() -> bool:
    """Check if GPU is available and working"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False