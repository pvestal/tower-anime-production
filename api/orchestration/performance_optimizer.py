"""
Performance Optimization Module for Animation Orchestration
Provides caching, connection pooling, and performance monitoring
"""

import asyncio
import time
import json
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import hashlib

import redis.asyncio as redis
from sqlalchemy.pool import QueuePool
import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics collection"""
    request_count: int = 0
    avg_response_time: float = 0.0
    cache_hit_rate: float = 0.0
    db_connection_usage: float = 0.0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    gpu_memory: float = 0.0
    active_jobs: int = 0
    queue_depth: int = 0

    # Time series data (last 100 samples)
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    cache_hits: deque = field(default_factory=lambda: deque(maxlen=100))
    system_resources: deque = field(default_factory=lambda: deque(maxlen=100))


class CacheManager:
    """Intelligent caching system for embeddings and workflows"""

    def __init__(self, redis_client: redis.Redis, default_ttl: int = 300):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.cache_stats = {'hits': 0, 'misses': 0, 'evictions': 0}

    async def get_cached_embedding(self, source_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached embedding by source hash"""
        try:
            cache_key = f"embedding:{source_hash}"
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                self.cache_stats['hits'] += 1
                return json.loads(cached_data)

            self.cache_stats['misses'] += 1
            return None

        except Exception as e:
            logger.error(f"Cache retrieval error: {e}")
            return None

    async def cache_embedding(self, source_hash: str, embedding_data: Dict[str, Any], ttl: Optional[int] = None):
        """Cache embedding with optional TTL"""
        try:
            cache_key = f"embedding:{source_hash}"
            ttl = ttl or self.default_ttl

            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(embedding_data, default=str)
            )

        except Exception as e:
            logger.error(f"Cache storage error: {e}")

    async def get_cached_workflow(self, workflow_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached compiled workflow"""
        try:
            cache_key = f"workflow:{workflow_hash}"
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                self.cache_stats['hits'] += 1
                return json.loads(cached_data)

            self.cache_stats['misses'] += 1
            return None

        except Exception as e:
            logger.error(f"Workflow cache retrieval error: {e}")
            return None

    async def cache_workflow(self, workflow_hash: str, workflow_data: Dict[str, Any], ttl: Optional[int] = None):
        """Cache compiled workflow"""
        try:
            cache_key = f"workflow:{workflow_hash}"
            ttl = ttl or self.default_ttl

            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(workflow_data, default=str)
            )

        except Exception as e:
            logger.error(f"Workflow cache storage error: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'hit_rate': hit_rate,
            'total_hits': self.cache_stats['hits'],
            'total_misses': self.cache_stats['misses'],
            'total_evictions': self.cache_stats['evictions']
        }


class ConnectionPoolManager:
    """Manages database and Redis connection pools"""

    def __init__(self, max_db_connections: int = 20, max_redis_connections: int = 10):
        self.max_db_connections = max_db_connections
        self.max_redis_connections = max_redis_connections
        self.db_pool_config = {
            'pool_size': max_db_connections,
            'max_overflow': 10,
            'pool_timeout': 30,
            'pool_recycle': 3600,  # 1 hour
            'pool_pre_ping': True
        }

    def get_db_pool_config(self) -> Dict[str, Any]:
        """Get optimized database pool configuration"""
        return self.db_pool_config

    async def create_redis_pool(self, redis_url: str) -> redis.ConnectionPool:
        """Create optimized Redis connection pool"""
        return redis.ConnectionPool.from_url(
            redis_url,
            max_connections=self.max_redis_connections,
            retry_on_timeout=True,
            socket_keepalive=True,
            socket_keepalive_options={
                1: 1,  # TCP_KEEPIDLE
                2: 3,  # TCP_KEEPINTVL
                3: 5,  # TCP_KEEPCNT
            }
        )


class PerformanceMonitor:
    """Real-time performance monitoring and optimization"""

    def __init__(self, collection_interval: float = 1.0):
        self.collection_interval = collection_interval
        self.metrics = PerformanceMetrics()
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.optimization_callbacks: List[Callable] = []

    async def start_monitoring(self):
        """Start performance monitoring"""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Performance monitoring started")

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Performance monitoring stopped")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                await self._collect_metrics()
                await self._check_optimization_triggers()
                await asyncio.sleep(self.collection_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(1.0)

    async def _collect_metrics(self):
        """Collect system and application metrics"""
        now = time.time()

        # System metrics
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Update metrics
        self.metrics.memory_usage = memory.percent
        self.metrics.cpu_usage = cpu_percent

        # Store time series data
        self.metrics.system_resources.append({
            'timestamp': now,
            'memory': memory.percent,
            'cpu': cpu_percent
        })

        # Try to get GPU memory if available
        try:
            import nvidia_ml_py3 as nvml
            nvml.nvmlInit()
            handle = nvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_memory_percent = (mem_info.used / mem_info.total) * 100
            self.metrics.gpu_memory = gpu_memory_percent
        except:
            self.metrics.gpu_memory = 0.0

    async def _check_optimization_triggers(self):
        """Check for conditions that trigger optimization"""
        # High memory usage
        if self.metrics.memory_usage > 80:
            logger.warning(f"High memory usage detected: {self.metrics.memory_usage:.1f}%")
            await self._trigger_optimization('high_memory')

        # High CPU usage
        if self.metrics.cpu_usage > 90:
            logger.warning(f"High CPU usage detected: {self.metrics.cpu_usage:.1f}%")
            await self._trigger_optimization('high_cpu')

        # Low cache hit rate
        if self.metrics.cache_hit_rate < 50:
            logger.warning(f"Low cache hit rate: {self.metrics.cache_hit_rate:.1f}%")
            await self._trigger_optimization('low_cache_hit_rate')

    async def _trigger_optimization(self, trigger_type: str):
        """Trigger optimization callbacks"""
        for callback in self.optimization_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(trigger_type, self.metrics)
                else:
                    callback(trigger_type, self.metrics)
            except Exception as e:
                logger.error(f"Optimization callback error: {e}")

    def add_optimization_callback(self, callback: Callable):
        """Add optimization callback function"""
        self.optimization_callbacks.append(callback)

    def record_request(self, response_time: float):
        """Record a request response time"""
        self.metrics.request_count += 1
        self.metrics.response_times.append(response_time)

        # Calculate rolling average
        if self.metrics.response_times:
            self.metrics.avg_response_time = sum(self.metrics.response_times) / len(self.metrics.response_times)

    def record_cache_operation(self, hit: bool):
        """Record cache hit/miss"""
        self.metrics.cache_hits.append(1 if hit else 0)

        # Calculate rolling hit rate
        if self.metrics.cache_hits:
            self.metrics.cache_hit_rate = (sum(self.metrics.cache_hits) / len(self.metrics.cache_hits)) * 100

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        return {
            'requests': {
                'total': self.metrics.request_count,
                'avg_response_time': self.metrics.avg_response_time,
                'current_response_times': list(self.metrics.response_times)[-10:]  # Last 10
            },
            'cache': {
                'hit_rate': self.metrics.cache_hit_rate,
                'recent_hits': list(self.metrics.cache_hits)[-10:]  # Last 10
            },
            'system': {
                'memory_usage': self.metrics.memory_usage,
                'cpu_usage': self.metrics.cpu_usage,
                'gpu_memory': self.metrics.gpu_memory
            },
            'jobs': {
                'active': self.metrics.active_jobs,
                'queue_depth': self.metrics.queue_depth
            }
        }


class WorkflowHasher:
    """Generates consistent hashes for caching workflows and embeddings"""

    @staticmethod
    def hash_scene_request(scene_request) -> str:
        """Generate hash for scene request for workflow caching"""
        # Extract relevant fields for hashing
        hashable_data = {
            'storyline_text': scene_request.storyline_text,
            'character_ids': sorted(scene_request.character_ids) if scene_request.character_ids else [],
            'conditions': [
                {
                    'type': condition.type.value if hasattr(condition.type, 'value') else str(condition.type),
                    'data': condition.data,
                    'weight': condition.weight
                }
                for condition in sorted(scene_request.conditions, key=lambda x: str(x.type))
            ],
            'output_format': scene_request.output_format,
            'resolution': scene_request.resolution,
            'style_preset': scene_request.style_preset
        }

        # Create hash
        json_str = json.dumps(hashable_data, sort_keys=True, default=str)
        return hashlib.md5(json_str.encode()).hexdigest()

    @staticmethod
    def hash_embedding_source(source: str, embedding_type: str) -> str:
        """Generate hash for embedding source"""
        combined = f"{embedding_type}:{source}"
        return hashlib.md5(combined.encode()).hexdigest()


class PerformanceOptimizer:
    """Main performance optimization coordinator"""

    def __init__(self, redis_client: redis.Redis):
        self.cache_manager = CacheManager(redis_client)
        self.pool_manager = ConnectionPoolManager()
        self.monitor = PerformanceMonitor()
        self.hasher = WorkflowHasher()

        # Setup optimization callbacks
        self.monitor.add_optimization_callback(self._handle_optimization_trigger)

    async def initialize(self):
        """Initialize performance optimization"""
        await self.monitor.start_monitoring()
        logger.info("Performance optimizer initialized")

    async def cleanup(self):
        """Cleanup performance optimization"""
        await self.monitor.stop_monitoring()
        logger.info("Performance optimizer cleaned up")

    async def _handle_optimization_trigger(self, trigger_type: str, metrics: PerformanceMetrics):
        """Handle optimization triggers"""
        if trigger_type == 'high_memory':
            logger.info("Triggering memory optimization")
            # Could implement memory cleanup, cache eviction, etc.

        elif trigger_type == 'high_cpu':
            logger.info("Triggering CPU optimization")
            # Could implement job throttling, worker adjustment, etc.

        elif trigger_type == 'low_cache_hit_rate':
            logger.info("Triggering cache optimization")
            # Could implement cache warming, TTL adjustment, etc.

    def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        return {
            'monitor': self.monitor.get_metrics_summary(),
            'cache': self.cache_manager.get_cache_stats(),
            'timestamp': datetime.now().isoformat()
        }