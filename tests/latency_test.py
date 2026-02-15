"""
URL Shortener - Python Latency Testing Script

This script provides detailed latency measurements with:
- Concurrent request testing
- Cache hit vs miss comparison
- Percentile calculations (P50, P95, P99)
- JSON/CSV output for analysis

Usage:
    python latency_test.py --url http://localhost:8000 --test quick
    python latency_test.py --url http://localhost:8000 --test full --concurrency 10
"""

import asyncio
import aiohttp
import argparse
import json
import time
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import random
import string


@dataclass
class LatencyResult:
    """Results from a latency test."""
    endpoint: str
    method: str
    iterations: int
    min_ms: float
    max_ms: float
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    success_rate: float
    errors: int


class LatencyTester:
    """Async latency tester for URL shortener."""
    
    def __init__(self, base_url: str, concurrency: int = 10):
        self.base_url = base_url.rstrip('/')
        self.concurrency = concurrency
        self.results: list[LatencyResult] = []
        self.test_short_code: Optional[str] = None
    
    async def check_health(self) -> bool:
        """Check if service is healthy."""
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.get(f"{self.base_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✓ Service healthy: {json.dumps(data)}")
                        return True
                    print(f"✗ Health check failed: {resp.status}")
                    return False
            except Exception as e:
                print(f"✗ Connection failed: {e}")
                return False
    
    async def create_test_url(self) -> str:
        """Create a test URL for benchmarking."""
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            data = {"url": f"https://example.com/latency-test-{int(time.time())}"}
            async with session.post(
                f"{self.base_url}/shorten",
                json=data
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    print(f"✗ Failed to create test URL: {resp.status} - {text}")
                    return None
                
                result = await resp.json()
                self.test_short_code = result.get('short_code')
                if not self.test_short_code:
                    print(f"✗ No short_code in response: {result}")
                    return None
                    
                print(f"✓ Created test URL: {self.test_short_code}")
                return self.test_short_code
    
    async def _single_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None
    ) -> tuple[float, bool]:
        """Make a single request and return latency in ms."""
        start = time.perf_counter()
        try:
            if method == "GET":
                async with session.get(
                    f"{self.base_url}{endpoint}",
                    allow_redirects=False
                ) as resp:
                    await resp.read()
                    success = resp.status in (200, 301, 302)
            else:
                async with session.post(
                    f"{self.base_url}{endpoint}",
                    json=json_data
                ) as resp:
                    await resp.read()
                    success = resp.status in (200, 201)
            
            latency_ms = (time.perf_counter() - start) * 1000
            return latency_ms, success
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            return latency_ms, False
    
    async def run_test(
        self,
        name: str,
        endpoint: str,
        method: str = "GET",
        json_data: Optional[dict] = None,
        iterations: int = 100
    ) -> LatencyResult:
        """Run latency test for an endpoint."""
        print(f"\n📊 Testing: {name}")
        print(f"   Endpoint: {method} {endpoint}")
        print(f"   Iterations: {iterations}, Concurrency: {self.concurrency}")
        
        latencies = []
        errors = 0
        
        connector = aiohttp.TCPConnector(limit=self.concurrency, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Warm up
            for _ in range(min(5, iterations)):
                await self._single_request(session, method, endpoint, json_data)
            
            # Run test
            semaphore = asyncio.Semaphore(self.concurrency)
            
            async def bounded_request():
                async with semaphore:
                    return await self._single_request(session, method, endpoint, json_data)
            
            tasks = [bounded_request() for _ in range(iterations)]
            results = await asyncio.gather(*tasks)
            
            for latency, success in results:
                latencies.append(latency)
                if not success:
                    errors += 1
        
        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p50_idx = int(len(sorted_latencies) * 0.50)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)
        
        result = LatencyResult(
            endpoint=endpoint,
            method=method,
            iterations=iterations,
            min_ms=round(min(latencies), 2),
            max_ms=round(max(latencies), 2),
            avg_ms=round(statistics.mean(latencies), 2),
            p50_ms=round(sorted_latencies[p50_idx], 2),
            p95_ms=round(sorted_latencies[p95_idx], 2),
            p99_ms=round(sorted_latencies[p99_idx], 2),
            success_rate=round((iterations - errors) / iterations * 100, 2),
            errors=errors
        )
        
        self._print_result(result)
        self.results.append(result)
        return result
    
    def _print_result(self, result: LatencyResult):
        """Print formatted result."""
        print(f"   ┌─────────────────────────────┐")
        print(f"   │ Min:     {result.min_ms:>8.2f} ms       │")
        print(f"   │ Max:     {result.max_ms:>8.2f} ms       │")
        print(f"   │ Avg:     {result.avg_ms:>8.2f} ms       │")
        print(f"   │ P50:     {result.p50_ms:>8.2f} ms       │")
        print(f"   │ P95:     {result.p95_ms:>8.2f} ms       │")
        print(f"   │ P99:     {result.p99_ms:>8.2f} ms       │")
        print(f"   │ Success: {result.success_rate:>7.1f}%        │")
        print(f"   └─────────────────────────────┘")
    
    async def run_quick_test(self):
        """Run a quick test with low iteration count."""
        print("\n" + "="*50)
        print("🚀 Quick Latency Test")
        print("="*50)
        
        await self.run_test("Health Check", "/health", iterations=20)
        await self.run_test(
            "Create URL", "/shorten", "POST",
            {"url": "https://example.com/quick-test"},
            iterations=20
        )
        await self.run_test(
            "Redirect (Cached)", f"/{self.test_short_code}",
            iterations=50
        )
        await self.run_test(
            "Get Stats", f"/stats/{self.test_short_code}",
            iterations=20
        )
    
    async def run_full_test(self):
        """Run comprehensive test with more iterations."""
        print("\n" + "="*50)
        print("🔥 Full Latency Test")
        print("="*50)
        
        await self.run_test("Health Check", "/health", iterations=100)
        
        await self.run_test(
            "Create URL", "/shorten", "POST",
            {"url": "https://example.com/full-test"},
            iterations=100
        )
        
        # Cold redirects (cache miss)
        print("\n📊 Testing: Redirect (Cold - Cache Miss)")
        cold_latencies = []
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            for i in range(20):
                # Create new URL each time
                rand_suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
                async with session.post(
                    f"{self.base_url}/shorten",
                    json={"url": f"https://example.com/cold-{rand_suffix}"}
                ) as resp:
                    data = await resp.json()
                    code = data['short_code']
                
                latency, _ = await self._single_request(session, "GET", f"/{code}")
                cold_latencies.append(latency)
        
        print(f"   Cold redirect avg: {statistics.mean(cold_latencies):.2f} ms")
        print(f"   Cold redirect P95: {sorted(cold_latencies)[int(len(cold_latencies)*0.95)]:.2f} ms")
        
        # Warm redirects (cache hit)
        await self.run_test(
            "Redirect (Warm - Cache Hit)", f"/{self.test_short_code}",
            iterations=500
        )
        
        await self.run_test(
            "Get Stats", f"/stats/{self.test_short_code}",
            iterations=100
        )
    
    async def run_load_test(self, duration_seconds: int = 30):
        """Run sustained load test."""
        print("\n" + "="*50)
        print(f"⚡ Load Test ({duration_seconds}s)")
        print("="*50)
        
        print(f"\nTarget: {self.base_url}/{self.test_short_code}")
        print(f"Concurrency: {self.concurrency}")
        
        latencies = []
        errors = 0
        start_time = time.time()
        request_count = 0
        
        connector = aiohttp.TCPConnector(limit=self.concurrency, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            while time.time() - start_time < duration_seconds:
                tasks = []
                for _ in range(self.concurrency):
                    tasks.append(self._single_request(
                        session, "GET", f"/{self.test_short_code}"
                    ))
                
                results = await asyncio.gather(*tasks)
                for latency, success in results:
                    latencies.append(latency)
                    request_count += 1
                    if not success:
                        errors += 1
                
                elapsed = time.time() - start_time
                rps = request_count / elapsed if elapsed > 0 else 0
                print(f"\r   Requests: {request_count}, RPS: {rps:.0f}, Errors: {errors}", end="")
        
        print("\n")
        
        # Final stats
        elapsed = time.time() - start_time
        rps = request_count / elapsed
        sorted_latencies = sorted(latencies)
        
        print(f"   ┌─────────────────────────────────┐")
        print(f"   │ Total Requests: {request_count:>15} │")
        print(f"   │ Duration:       {elapsed:>12.1f}s │")
        print(f"   │ RPS:            {rps:>15.0f} │")
        print(f"   │ Errors:         {errors:>15} │")
        print(f"   │ Avg Latency:    {statistics.mean(latencies):>12.2f}ms │")
        print(f"   │ P50 Latency:    {sorted_latencies[int(len(sorted_latencies)*0.50)]:>12.2f}ms │")
        print(f"   │ P95 Latency:    {sorted_latencies[int(len(sorted_latencies)*0.95)]:>12.2f}ms │")
        print(f"   │ P99 Latency:    {sorted_latencies[int(len(sorted_latencies)*0.99)]:>12.2f}ms │")
        print(f"   └─────────────────────────────────┘")
    
    def save_results(self, filename: str = None):
        """Save results to JSON file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test-results/latency_{timestamp}.json"
        
        import os
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")


async def main():
    parser = argparse.ArgumentParser(description="URL Shortener Latency Tester")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--test", choices=["quick", "full", "load", "all"], default="quick")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--duration", type=int, default=30, help="Load test duration (seconds)")
    
    args = parser.parse_args()
    
    print("="*50)
    print("🔬 URL Shortener Latency Tester")
    print("="*50)
    print(f"Target: {args.url}")
    print(f"Test: {args.test}")
    print(f"Concurrency: {args.concurrency}")
    
    tester = LatencyTester(args.url, args.concurrency)
    
    if not await tester.check_health():
        print("❌ Service not available. Exiting.")
        return
    
    await tester.create_test_url()
    
    if args.test == "quick":
        await tester.run_quick_test()
    elif args.test == "full":
        await tester.run_full_test()
    elif args.test == "load":
        await tester.run_load_test(args.duration)
    elif args.test == "all":
        await tester.run_full_test()
        await tester.run_load_test(args.duration)
    
    tester.save_results()
    
    print("\n" + "="*50)
    print("✅ Testing Complete!")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
