#!/usr/bin/env python3
"""
Test Generation Cache Performance
"""
import time
import asyncio
import hashlib
import json
import random
import asyncpg
from datetime import datetime

class CachePerformanceTester:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'tower_echo_brain_secret_key_2025'
        }

    async def connect_db(self):
        return await asyncpg.connect(**self.db_config)

    def generate_cache_key(self, params):
        """Generate cache key from parameters"""
        return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

    async def simulate_cache_lookup(self, conn, params):
        """Simulate a cache lookup"""
        cache_key = self.generate_cache_key(params)

        # Check cache
        cached = await conn.fetchrow('''
            SELECT * FROM generation_cache
            WHERE output_hash = $1 OR (
                character_id = (SELECT id FROM characters LIMIT 1)
                AND action_id = $2
            )
            LIMIT 1
        ''', cache_key, params.get('action_id', 1))

        return cached is not None

    async def simulate_cache_write(self, conn, params):
        """Simulate writing to cache"""
        cache_key = self.generate_cache_key(params)

        try:
            await conn.execute('''
                INSERT INTO generation_cache (
                    output_hash, positive_prompt, seed,
                    base_model, quality_score, generation_time_ms,
                    created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (output_hash) DO NOTHING
            ''', cache_key, params.get('prompt', 'test'),
                params.get('seed', 42),
                'animagine-xl-3.0.safetensors',
                random.uniform(0.6, 0.95),
                random.randint(2000, 8000),
                datetime.now())
            return True
        except:
            return False

    async def benchmark_cache(self):
        """Run cache performance benchmarks"""
        print("🔍 Benchmarking Generation Cache...")
        print("=" * 50)

        # Create connection pool for concurrent operations
        pool = await asyncpg.create_pool(**self.db_config, min_size=5, max_size=20)
        conn = await self.connect_db()

        # Test 1: Single lookup (cold cache)
        test_params = {
            'character': 'Mei',
            'action_id': 1,
            'style': 'intimate_soft',
            'seed': 42
        }

        start = time.time()
        hit = await self.simulate_cache_lookup(conn, test_params)
        lookup_time = (time.time() - start) * 1000
        print(f"1. Cold cache lookup: {lookup_time:.2f}ms ({'HIT' if hit else 'MISS'})")

        # Test 2: Write to cache
        start = time.time()
        written = await self.simulate_cache_write(conn, test_params)
        write_time = (time.time() - start) * 1000
        print(f"2. Cache write: {write_time:.2f}ms ({'SUCCESS' if written else 'EXISTS'})")

        # Test 3: Warm cache lookup
        start = time.time()
        hit = await self.simulate_cache_lookup(conn, test_params)
        warm_lookup_time = (time.time() - start) * 1000
        print(f"3. Warm cache lookup: {warm_lookup_time:.2f}ms ({'HIT' if hit else 'MISS'})")

        if lookup_time > 0:
            speedup = lookup_time / warm_lookup_time if warm_lookup_time > 0 else float('inf')
            print(f"   Speedup: {speedup:.1f}x")

        # Test 4: Concurrent lookups
        print("\n4. Testing concurrent cache operations...")
        tasks = []
        n_concurrent = 50

        async def concurrent_lookup(params):
            async with pool.acquire() as conn:
                return await self.simulate_cache_lookup(conn, params)

        for i in range(n_concurrent):
            params = test_params.copy()
            params['seed'] = random.randint(1, 1000)
            params['action_id'] = random.randint(1, 17)  # We have 17 semantic actions
            tasks.append(concurrent_lookup(params))

        start = time.time()
        results = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start
        hit_count = sum(1 for r in results if r)

        print(f"   {n_concurrent} concurrent lookups: {concurrent_time*1000:.2f}ms total")
        print(f"   Throughput: {n_concurrent/concurrent_time:.1f} req/sec")
        print(f"   Cache hit rate: {hit_count/n_concurrent*100:.1f}%")

        # Test 5: Database statistics
        stats = await conn.fetchrow('''
            SELECT
                COUNT(*) as total_entries,
                AVG(quality_score) as avg_quality,
                AVG(generation_time_ms) as avg_gen_time
            FROM generation_cache
        ''')

        print("\n📊 Cache Statistics:")
        print(f"   Total entries: {stats['total_entries']}")
        if stats['avg_quality']:
            print(f"   Avg quality: {stats['avg_quality']:.2f}")
        if stats['avg_gen_time']:
            print(f"   Avg generation time: {stats['avg_gen_time']:.0f}ms")

        # Performance summary
        print("\n" + "=" * 50)
        print("📈 PERFORMANCE SUMMARY:")

        if warm_lookup_time < 100:
            print("✅ Cache lookups: FAST (<100ms)")
        elif warm_lookup_time < 500:
            print("⚠️  Cache lookups: MODERATE (100-500ms)")
        else:
            print("❌ Cache lookups: SLOW (>500ms)")

        if n_concurrent/concurrent_time > 50:
            print("✅ Throughput: EXCELLENT (>50 req/sec)")
        elif n_concurrent/concurrent_time > 10:
            print("⚠️  Throughput: GOOD (10-50 req/sec)")
        else:
            print("❌ Throughput: NEEDS OPTIMIZATION (<10 req/sec)")

        print("=" * 50)

        await conn.close()
        await pool.close()

if __name__ == "__main__":
    tester = CachePerformanceTester()
    asyncio.run(tester.benchmark_cache())