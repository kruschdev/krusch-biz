#!/usr/bin/env python3
"""
scripts/cache_bge_embeddings.py
===============================
Compute and freeze real 1024-dimension bge-large vector embeddings for:
  1. Seed commercial fixtures (seed_bge_large.json)
  2. Golden evaluation benchmark queries (queries_bge_large.json)
  3. Held-out contracts & evaluation queries (heldout_bge_large.json)
Allows CI gates and unit tests to run unmocked cosine retrieval without live Ollama.
"""

import json
import os
import sys
import httpx

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.ingest import SEED_COMMERCIAL_FIXTURES

OLLAMA_URL = os.getenv("OLLAMA_EMBED_HOST", "http://localhost:11434")
MODEL_NAME = "bge-large"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_embedding(client: httpx.Client, text: str) -> list[float]:
    resp = client.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": MODEL_NAME, "prompt": text},
        timeout=60.0
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def main():
    print(f"Connecting to Ollama at {OLLAMA_URL} with model '{MODEL_NAME}'...")
    with httpx.Client() as client:
        # 1. Seed fixtures
        print("Caching embeddings for seed commercial fixtures...")
        seed_cache = {}
        for item in SEED_COMMERCIAL_FIXTURES:
            sec = item["section"]
            content = item["content"]
            print(f"  Embedding seed clause: {sec}...")
            vec = get_embedding(client, content)
            seed_cache[sec] = vec

        seed_path = os.path.join(OUTPUT_DIR, "seed_bge_large.json")
        with open(seed_path, "w", encoding="utf-8") as f:
            json.dump(seed_cache, f)
        print(f"Saved {len(seed_cache)} seed embeddings to {seed_path}")

        # 2. Golden eval queries
        eval_path = os.path.join(PROJECT_ROOT, "data", "eval", "golden_business_eval.json")
        with open(eval_path, "r", encoding="utf-8") as f:
            golden_cases = json.load(f)

        print("Caching embeddings for golden eval queries...")
        query_cache = {}
        for c in golden_cases:
            q_id = c["id"]
            q_text = c.get("fact_pattern") or c.get("query")
            print(f"  Embedding query [{q_id}]: {q_text[:40]}...")
            vec = get_embedding(client, q_text)
            query_cache[q_id] = vec

        queries_path = os.path.join(OUTPUT_DIR, "queries_bge_large.json")
        with open(queries_path, "w", encoding="utf-8") as f:
            json.dump(query_cache, f)
        print(f"Saved {len(query_cache)} query embeddings to {queries_path}")

        # 3. Heldout contracts
        heldout_path = os.path.join(PROJECT_ROOT, "data", "eval", "heldout_contracts.json")
        with open(heldout_path, "r", encoding="utf-8") as f:
            heldout_cases = json.load(f)

        print("Caching embeddings for held-out contracts and queries...")
        heldout_cache = {}
        for c in heldout_cases:
            hid = c["id"]
            q_text = c["query"]
            print(f"  Embedding heldout query [{hid}]: {q_text[:40]}...")
            q_vec = get_embedding(client, q_text)
            heldout_cache[f"q_{hid}"] = q_vec

            cl = c.get("clause_fixture")
            if cl:
                c_sec = cl["section"]
                c_content = cl["content"]
                c_vec = get_embedding(client, c_content)
                heldout_cache[f"c_{c_sec}"] = c_vec

            pred = c.get("predecessor_fixture")
            if pred:
                p_sec = pred["section"]
                p_content = pred["content"]
                p_vec = get_embedding(client, p_content)
                heldout_cache[f"c_{p_sec}"] = p_vec

        heldout_out = os.path.join(OUTPUT_DIR, "heldout_bge_large.json")
        with open(heldout_out, "w", encoding="utf-8") as f:
            json.dump(heldout_cache, f)
        print(f"Saved {len(heldout_cache)} held-out embeddings to {heldout_out}")

    print("\n[SUCCESS] Frozen bge-large local embedding cache complete.")


if __name__ == "__main__":
    main()
