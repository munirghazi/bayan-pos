#!/usr/bin/env python3
"""Bayan POS — load / stress test.  LOCAL COPY ONLY.

Oracle's testing policy forbids load testing against any Oracle Cloud asset,
including your own server: never point this at sahlpos.roaa.sa.

Needs:  pip install httpx      Prepare data first with setup_local.py.

    python3 stress_test.py --config config.local.json                    # all phases
    python3 stress_test.py --config config.local.json --phase realistic  # one phase

Phases
  login      every cashier logs in at the same moment (morning opening)
  realistic  20 cashiers, 2–6 s between actions, a sale every few actions
  peak       20 cashiers with no pause at all (worst-case rush)
  breaking   no pause, 20 → 40 → 80 → 160 concurrent users, 45 s each,
             to find where it slows down (p95 > 2 s) or errors (> 1 %)
  integrity  after the load: invoice numbers per branch must be unique and gapless

Each simulated cashier loops:  product list → (search) → issue a sale
(cash / card / split) → sometimes invoice search, sometimes a report.
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Install httpx first:  pip install httpx")

if sys.version_info < (3, 9):
    sys.exit("Python 3.9+ needed")


class Stats:
    def __init__(self):
        self.lat = defaultdict(list)
        self.err = defaultdict(int)
        self.err_samples = defaultdict(list)
        self.count = defaultdict(int)
        self.start = time.perf_counter()

    def add(self, name, ms, ok, detail=""):
        self.count[name] += 1
        self.lat[name].append(ms)
        if not ok:
            self.err[name] += 1
            if len(self.err_samples[name]) < 3:
                self.err_samples[name].append(detail[:160])

    def summary(self):
        dur = time.perf_counter() - self.start
        rows = []
        all_lat = []
        for name in sorted(self.count):
            l = sorted(self.lat[name])
            all_lat += l
            rows.append({"action": name, "count": self.count[name], "errors": self.err[name],
                         "p50": pct(l, 50), "p95": pct(l, 95), "p99": pct(l, 99), "max": round(l[-1]) if l else 0,
                         "samples": self.err_samples[name]})
        total = sum(self.count.values())
        errors = sum(self.err.values())
        all_lat.sort()
        return {"seconds": round(dur, 1), "requests": total, "rps": round(total / dur, 1) if dur else 0,
                "errors": errors, "error_pct": round(100 * errors / total, 2) if total else 0,
                "p50": pct(all_lat, 50), "p95": pct(all_lat, 95), "p99": pct(all_lat, 99),
                "sales": self.count.get("sale", 0) - self.err.get("sale", 0), "rows": rows}


def pct(l, p):
    if not l:
        return 0
    k = max(0, min(len(l) - 1, int(round(p / 100 * len(l) + 0.5)) - 1))
    return round(l[k])


async def timed(stats, name, coro):
    t = time.perf_counter()
    try:
        r = await coro
        ok = r.status_code < 400
        stats.add(name, (time.perf_counter() - t) * 1000, ok, f"{r.status_code} {r.text[:120]}" if not ok else "")
        return r
    except Exception as e:
        stats.add(name, (time.perf_counter() - t) * 1000, False, f"{type(e).__name__}: {e}")
        return None


async def login(client, stats, tenant, user, pw):
    r = await timed(stats, "login", client.post("/api/auth/login", json={"tenant": tenant, "username": user, "password": pw}))
    if r is None or r.status_code != 200:
        return None
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def cashier(base, stats, tenant, user, pw, products, stop_at, think, sem=None):
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=4, keepalive_expiry=4)
    async with httpx.AsyncClient(base_url=base, timeout=60, limits=limits) as c:
        h = await login(c, stats, tenant, user, pw)
        if not h:
            return
        n = 0
        while time.perf_counter() < stop_at:
            n += 1
            await timed(stats, "products", c.get("/api/products/", headers=h))
            if n % 3 == 0:
                await timed(stats, "product_search", c.get("/api/products/", headers=h, params={"search": "LOAD"}))
            items, total = [], 0.0
            for p in random.sample(products, k=random.randint(1, min(4, len(products)))):
                q = random.randint(1, 3)
                items.append({"product_id": p["id"], "quantity": q})
                total += p["price"] * q
            kind = random.random()
            if kind < 0.6:
                pays = [{"method": "cash", "amount": round(total + random.choice([0, 0, 5, 50]), 2)}]
            elif kind < 0.9:
                pays = [{"method": "card", "amount": round(total, 2), "card_ref": f"L{random.randint(100000, 999999)}"}]
            else:
                half = round(total / 2, 2)
                pays = [{"method": "card", "amount": half, "card_ref": f"S{random.randint(100000, 999999)}"},
                        {"method": "cash", "amount": round(total - half + 10, 2)}]
            await timed(stats, "sale", c.post("/api/sales/", headers=h, json={"items": items, "payments": pays}))
            if n % 5 == 0:
                await timed(stats, "invoice_search", c.get("/api/sales/search", headers=h, params={"limit": 20}))
            if n % 10 == 0:
                day = datetime.utcfromtimestamp(time.time() + 3 * 3600).strftime("%Y-%m-%d")   # today in Riyadh
                await timed(stats, "report", c.get("/api/reports/sales-report", headers=h,
                                                   params={"start_date": day, "end_date": day}))
            if n % 10 == 5:
                await timed(stats, "dashboard", c.get("/api/reports/dashboard", headers=h))
            if think:
                await asyncio.sleep(random.uniform(*think))


async def prepare_products(base, cfg):
    """Make sure each load tenant has 30 products with big stock; return {slug: [products]}."""
    out = {}
    async with httpx.AsyncClient(base_url=base, timeout=60) as c:
        for t in cfg["load_tenants"]:
            r = await c.post("/api/auth/login", json={"tenant": t["slug"], "username": t["admin"], "password": cfg["password"]})
            r.raise_for_status()
            c.cookies.clear()
            h = {"Authorization": f"Bearer {r.json()['access_token']}"}
            prods = [p for p in (await c.get("/api/products/", headers=h)).json() if p["name"].startswith("LOAD-")]
            for i in range(len(prods), 30):
                r = await c.post("/api/products/", headers=h, json={"name": f"LOAD-{i:02d}", "price": random.choice([5, 9.5, 12, 23, 49, 115]),
                                                                   "stock": 1_000_000})
                r.raise_for_status()
                prods.append(r.json())
            for p in prods:
                if p.get("stock", 0) < 100_000:
                    await c.put(f"/api/products/{p['id']}/stock", headers=h, params={"quantity": 1_000_000})
            out[t["slug"]] = [{"id": p["id"], "price": float(p["price"])} for p in prods]
    return out


def users_list(cfg, n):
    """n cashier identities spread over the load tenants (re-using users when n is larger)."""
    flat = [(t["slug"], u) for t in cfg["load_tenants"] for u in t["cashiers"]]
    return [flat[i % len(flat)] for i in range(n)]


async def run_phase(name, cfg, products, users, seconds, think):
    stats = Stats()
    stop_at = time.perf_counter() + seconds
    tasks = [cashier(cfg["base"], stats, t, u, cfg["password"], products[t], stop_at, think) for t, u in users]
    await asyncio.gather(*tasks)
    s = stats.summary()
    s["phase"], s["users"] = name, len(users)
    print_summary(s)
    return s


async def login_burst(cfg, n):
    stats = Stats()

    async def one(t, u):
        async with httpx.AsyncClient(base_url=cfg["base"], timeout=60) as c:
            await login(c, stats, t, u, cfg["password"])
    await asyncio.gather(*[one(t, u) for t, u in users_list(cfg, n)])
    s = stats.summary()
    s["phase"], s["users"] = "login", n
    print_summary(s)
    return s


def print_summary(s):
    print(f"\n=== {s['phase']}  ({s['users']} users, {s['seconds']} s) ===")
    print(f"requests {s['requests']}  ·  {s['rps']} req/s  ·  sales issued {s['sales']}  ·  errors {s['errors']} ({s['error_pct']} %)")
    print(f"latency ms  p50 {s['p50']}  p95 {s['p95']}  p99 {s['p99']}")
    print(f"{'action':<16}{'count':>7}{'err':>6}{'p50':>7}{'p95':>7}{'p99':>7}{'max':>7}")
    for r in s["rows"]:
        print(f"{r['action']:<16}{r['count']:>7}{r['errors']:>6}{r['p50']:>7}{r['p95']:>7}{r['p99']:>7}{r['max']:>7}")
        for e in r["samples"]:
            print(f"      ! {e}")


async def integrity(cfg):
    """Every load tenant: invoice numbers unique and gapless per branch prefix."""
    problems, checked = [], 0
    async with httpx.AsyncClient(base_url=cfg["base"], timeout=120) as c:
        for t in cfg["load_tenants"]:
            r = await c.post("/api/auth/login", json={"tenant": t["slug"], "username": t["admin"], "password": cfg["password"]})
            c.cookies.clear()
            h = {"Authorization": f"Bearer {r.json()['access_token']}"}
            numbers, offset = [], 0
            while True:
                page = (await c.get("/api/sales/search", headers=h, params={"limit": 200, "offset": offset})).json()
                rows = page["rows"]
                numbers += [x["invoice_number"] for x in rows]
                offset += len(rows)
                if not rows or offset >= page["count"]:
                    break
            by_prefix = defaultdict(list)
            for num in numbers:
                prefix, seq = num.rsplit("-", 1)
                by_prefix[prefix].append(int(seq))
            for prefix, seqs in by_prefix.items():
                checked += len(seqs)
                dup = len(seqs) - len(set(seqs))
                missing = sorted(set(range(1, max(seqs) + 1)) - set(seqs))
                if dup or missing:
                    problems.append(f"{t['slug']} {prefix}: duplicates={dup} missing={missing[:10]}")
    ok = not problems
    print(f"\n=== integrity: {checked} invoices checked — {'OK, unique and gapless' if ok else 'PROBLEMS'} ===")
    for p in problems:
        print("   ! " + p)
    return {"phase": "integrity", "invoices": checked, "ok": ok, "problems": problems}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--phase", choices=["all", "login", "realistic", "peak", "breaking", "integrity"], default="all")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--ramp", default="", help="breaking phase user counts, e.g. 80,160 (default: users ×1,2,4,8)")
    args = ap.parse_args()
    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text())
    if cfg.get("mode") == "live" or "roaa.sa" in cfg["base"]:
        sys.exit("Refusing: load testing the Oracle-hosted server is forbidden by Oracle's policy. Use a local copy.")

    print(f"Target {cfg['base']}  ·  {len(cfg['load_tenants'])} tenants  ·  target {args.users} cashiers")
    products = await prepare_products(cfg["base"], cfg)
    results = []
    ph = args.phase
    if ph in ("all", "login"):
        results.append(await login_burst(cfg, args.users))
    if ph in ("all", "realistic"):
        results.append(await run_phase("realistic", cfg, products, users_list(cfg, args.users), args.seconds, (2, 6)))
    if ph in ("all", "peak"):
        results.append(await run_phase("peak", cfg, products, users_list(cfg, args.users), min(args.seconds, 90), None))
    if ph in ("all", "breaking"):
        steps = [int(x) for x in args.ramp.split(",") if x.strip()] or [args.users, args.users * 2, args.users * 4, args.users * 8]
        for n in steps:
            s = await run_phase(f"breaking-{n}", cfg, products, users_list(cfg, n), 45, None)
            results.append(s)
            if s["error_pct"] > 5 or s["p95"] > 10000:
                print("   stopping the ramp: the system is past its limit")
                break
    if ph in ("all", "integrity", "breaking", "peak", "realistic"):
        results.append(await integrity(cfg))

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = cfg_path.parent / f"stress-report-{stamp}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    asyncio.run(main())
