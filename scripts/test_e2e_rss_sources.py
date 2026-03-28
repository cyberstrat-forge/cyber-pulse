#!/usr/bin/env python3
"""End-to-end test for problematic RSS sources from issues directory.

Tests all sources from issues/2026-03-24-rss-no-content.md and
issues/2026-03-24-rss-source-accessibility.md.
"""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime

import httpx

# API configuration
API_URL = "http://localhost:8000"
ADMIN_KEY = None  # Will be read from config file


def get_admin_key():
    """Read admin key from config file."""
    global ADMIN_KEY
    if ADMIN_KEY:
        return ADMIN_KEY

    try:
        with open("/Users/luoweirong/.config/cyber-pulse/config") as f:
            for line in f:
                if line.startswith("admin_key="):
                    ADMIN_KEY = line.strip().split("=", 1)[1]
                    return ADMIN_KEY
    except FileNotFoundError:
        pass

    # Try to get from environment
    import os
    ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
    return ADMIN_KEY


def create_source(name: str, feed_url: str, tier: str = "T2") -> str:
    """Create a test source and return its ID."""
    admin_key = get_admin_key()
    headers = {"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"}

    data = {
        "name": f"[Test] {name}",
        "connector_type": "rss",
        "tier": tier,
        "config": {"feed_url": feed_url},
    }

    response = httpx.post(f"{API_URL}/api/v1/admin/sources", json=data, headers=headers)
    if response.status_code == 201:
        return response.json()["source_id"]
    elif response.status_code == 409:
        # Source already exists, get its ID
        resp = httpx.get(f"{API_URL}/api/v1/admin/sources", headers=headers)
        for src in resp.json():
            if src["name"] == f"[Test] {name}":
                return src["source_id"]
    else:
        print(f"  Error creating source: {response.status_code} - {response.text}")
        return None


def trigger_ingestion(source_id: str) -> str:
    """Trigger ingestion for a source and return job ID."""
    admin_key = get_admin_key()
    headers = {"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"}

    data = {"type": "ingest", "source_id": source_id}

    response = httpx.post(f"{API_URL}/api/v1/admin/jobs", json=data, headers=headers)
    if response.status_code == 201:
        return response.json()["job_id"]
    else:
        print(f"  Error triggering ingestion: {response.status_code}")
        return None


def wait_for_job(job_id: str, timeout: int = 300) -> dict:
    """Wait for job to complete and return status."""
    admin_key = get_admin_key()
    headers = {"Authorization": f"Bearer {admin_key}"}

    start = time.time()
    while time.time() - start < timeout:
        response = httpx.get(f"{API_URL}/api/v1/admin/jobs/{job_id}", headers=headers)
        if response.status_code == 200:
            job = response.json()
            if job["status"] in ["completed", "failed"]:
                return job
        time.sleep(2)

    return {"status": "timeout"}


def get_source_stats(source_id: str) -> dict:
    """Get statistics for a source."""
    admin_key = get_admin_key()
    headers = {"Authorization": f"Bearer {admin_key}"}

    # Get items count
    response = httpx.get(
        f"{API_URL}/api/v1/admin/items",
        params={"source_id": source_id, "limit": 1000},
        headers=headers,
    )

    items = response.json() if response.status_code == 200 else []

    mapped = sum(1 for i in items if i.get("status") == "MAPPED")
    rejected = sum(1 for i in items if i.get("status") == "REJECTED")
    pending = sum(1 for i in items if i.get("status") == "PENDING_FULL_FETCH")

    # Get word counts
    word_counts = [i.get("word_count", 0) for i in items if i.get("status") == "MAPPED" and i.get("word_count")]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0

    # Full fetch stats
    ff_attempted = sum(1 for i in items if i.get("full_fetch_attempted"))
    ff_succeeded = sum(1 for i in items if i.get("full_fetch_succeeded"))

    return {
        "total": len(items),
        "mapped": mapped,
        "rejected": rejected,
        "pending_ff": pending,
        "avg_words": avg_words,
        "ff_attempted": ff_attempted,
        "ff_succeeded": ff_succeeded,
        "success_rate": mapped / len(items) * 100 if items else 0,
    }


# Test sources from issues directory
TEST_SOURCES = [
    # Category 1: RSS Feed only provides title and link
    ("Paul Graham", "http://www.aaronsw.com/2002/feeds/pgessays.rss"),
    ("Fabien Sanglard", "https://fabiensanglard.net/rss.xml"),
    ("Mitchell Hashimoto", "https://mitchellh.com/feed.xml"),
    ("Chad Nauseam", "https://chadnauseam.com/rss.xml"),
    ("Google Cloud Security", "https://cloudblog.withgoogle.com/products/identity-security/rss/"),
    ("Eric Migicovsky", "https://ericmigi.com/rss.xml"),
    ("Beej's Guide", "https://beej.us/blog/rss.xml"),
    ("Jyn.dev", "https://jyn.dev/atom.xml"),
    ("Group-IB", "https://www.group-ib.com/feed/blogfeed/"),
    # Category 2: Short content
    ("Daniel Wirtz", "https://danielwirtz.com/feed/"),
    # Category 3: URL migration
    ("Microsoft Security", "https://www.microsoft.com/en-us/security/blog/feed/"),
    ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
    ("CSO Online", "https://www.csoonline.com/feed/"),
    # Category 4: Anti-crawl
    ("Dark Reading", "https://www.darkreading.com/rss.xml"),
    ("Karpathy Blog", "https://karpathy.bearblog.dev/feed/"),
    # Category 5: Connection issues
    ("Auth0 Blog", "https://auth0.com/blog/feed.xml"),
    ("Sysdig Blog", "https://www.sysdig.com/feed/"),
    ("Ted Unangst", "https://www.tedunangst.com/flak/rss"),
    ("Rachel by the Bay", "https://rachelbythebay.com/w/atom.xml"),
]


def main():
    print("=" * 60)
    print("End-to-End Test for Problematic RSS Sources")
    print("=" * 60)
    print()

    results = []

    for name, feed_url in TEST_SOURCES:
        print(f"Testing: {name}")
        print(f"  Feed: {feed_url}")

        # Create source
        source_id = create_source(name, feed_url)
        if not source_id:
            print(f"  ❌ Failed to create source")
            results.append({"name": name, "status": "error", "error": "Failed to create source"})
            continue

        print(f"  Source ID: {source_id}")

        # Trigger ingestion
        job_id = trigger_ingestion(source_id)
        if not job_id:
            print(f"  ❌ Failed to trigger ingestion")
            results.append({"name": name, "status": "error", "error": "Failed to trigger ingestion"})
            continue

        print(f"  Job ID: {job_id}")

        # Wait for job (with extended timeout for rate-limited sources)
        print(f"  Waiting for ingestion...")
        job = wait_for_job(job_id, timeout=600)  # 10 minutes max

        if job["status"] == "timeout":
            print(f"  ⏱️ Job timeout")
            results.append({"name": name, "status": "timeout"})
            continue

        if job["status"] == "failed":
            print(f"  ❌ Job failed: {job.get('error_message', 'Unknown error')}")
            results.append({"name": name, "status": "failed", "error": job.get("error_message")})
            continue

        # Wait a bit for all items to be processed (normalization, quality check, full fetch)
        print(f"  Waiting for processing...")
        time.sleep(30)  # Give time for full content fetch to complete

        # Get stats
        stats = get_source_stats(source_id)

        print(f"  Results: {stats['mapped']}/{stats['total']} MAPPED ({stats['success_rate']:.0f}%)")
        print(f"  Full Fetch: {stats['ff_succeeded']}/{stats['ff_attempted']} succeeded")
        print(f"  Avg Words: {stats['avg_words']:.0f}")
        print()

        results.append(
            {
                "name": name,
                "status": "completed",
                "source_id": source_id,
                **stats,
            }
        )

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    completed = [r for r in results if r["status"] == "completed"]
    errors = [r for r in results if r["status"] != "completed"]

    total_items = sum(r.get("total", 0) for r in completed)
    total_mapped = sum(r.get("mapped", 0) for r in completed)
    total_rejected = sum(r.get("rejected", 0) for r in completed)

    print(f"Sources tested: {len(results)}")
    print(f"Completed: {len(completed)}, Errors: {len(errors)}")
    print(f"Total items: {total_items}")
    print(f"Mapped: {total_mapped} ({total_mapped/total_items*100:.1f}%)" if total_items else "Mapped: 0")
    print(f"Rejected: {total_rejected}")
    print()

    # Categorize results
    perfect = [r for r in completed if r.get("success_rate", 0) == 100]
    good = [r for r in completed if 80 <= r.get("success_rate", 0) < 100]
    partial = [r for r in completed if 50 <= r.get("success_rate", 0) < 80]
    failed = [r for r in completed if r.get("success_rate", 0) < 50]

    print("✅ Perfect (100%):")
    for r in perfect:
        print(f"   {r['name']}: {r['mapped']} items, {r['avg_words']:.0f} avg words")

    print()
    print("🟢 Good (80-99%):")
    for r in good:
        print(f"   {r['name']}: {r['mapped']}/{r['total']} ({r['success_rate']:.0f}%), {r['avg_words']:.0f} avg words")

    print()
    print("🟡 Partial (50-79%):")
    for r in partial:
        print(f"   {r['name']}: {r['mapped']}/{r['total']} ({r['success_rate']:.0f}%), {r['avg_words']:.0f} avg words")

    print()
    print("🔴 Failed (<50%):")
    for r in failed:
        print(f"   {r['name']}: {r['mapped']}/{r['total']} ({r['success_rate']:.0f}%)")

    print()
    print("❌ Errors:")
    for r in errors:
        print(f"   {r['name']}: {r.get('error', r['status'])}")


if __name__ == "__main__":
    main()