# CI Pipeline Optimization Analysis (Staging Branch)

## Current Workflows on Staging

The staging branch has 3 workflow files (identical to main):

| Workflow | File | Trigger | ~Duration |
|---|---|---|---|
| **Build** | `nextjs.yml` | All PRs + push to main | **~1 min** |
| **Playwright Tests** | `playwright.yml` | PRs + push to main/staging | **~10 min** (x2 shards) |
| **Release image** | `release-image.yml` | Tags + main push | release-only |

Additionally, **CodeQL** runs on staging pushes.

## Playwright Tests — The Bottleneck

This is the critical path. It runs 2 shards in parallel, each taking ~10 min. Measured from recent staging runs:

| Step | Shard 1 | Shard 2 | % of total |
|---|---|---|---|
| **Seed test data into FalkorDB** | **223s** | **220s** | **37%** |
| **Run Playwright tests** | 264s | 262s | 44% |
| **Install Playwright browsers** | 48s | 51s | 8% |
| Install backend deps (`pip install`) | 28s | 31s | 5% |
| Build frontend | 12s | 12s | 2% |
| Install frontend deps (`npm ci`) | 8s | 8s | 1% |
| Container init + setup | ~15s | ~15s | 3% |

**Total per shard: ~600s (10 min). Total billable: ~20 min.**

## Build Workflow — Wasted Work

The Build workflow (~64s total) installs backend dependencies but does nothing with them:

| Step | Duration |
|---|---|
| Install frontend deps | 7s |
| Build frontend | 14s |
| Lint frontend | <1s |
| **Install backend deps (`pip install`)** | **35s** |

The backend install accounts for **55% of the Build workflow** and serves no purpose.

---

## Optimization Recommendations

### 1. Cache or pre-seed FalkorDB test data (saves **~3.5 min/shard = ~7 min total**)

`seed_test_data.py` clones 2 GitHub repos (GraphRAG-SDK, Flask) and runs full source analysis every run. This is the single biggest time sink at **37% of Playwright runtime**.

**Options:**
- **Best**: Export the seeded graph as an RDB dump, commit it as a test fixture, and restore with `redis-cli`. Eliminates the 220s step entirely.
- **Good**: Cache the cloned repos + analysis output with `actions/cache` keyed on the seed script hash + repo commit SHAs.
- **Minimum**: Cache just the git clones to skip network time.

### 2. Cache Playwright browsers (saves **~50s/shard = ~1.5 min total**)

Browsers are installed from scratch every run (`npx playwright install --with-deps`). Add:

```yaml
- name: Cache Playwright browsers
  id: playwright-cache
  uses: actions/cache@v4
  with:
    path: ~/.cache/ms-playwright
    key: playwright-${{ runner.os }}-${{ hashFiles('package-lock.json') }}

- name: Install Playwright Browsers
  if: steps.playwright-cache.outputs.cache-hit != 'true'
  run: npx playwright install --with-deps chromium

- name: Install Playwright system deps
  if: steps.playwright-cache.outputs.cache-hit == 'true'
  run: npx playwright install-deps chromium
```

### 3. Switch `pip install` to `uv` (saves **~15-20s/shard**)

Both workflows use slow `pip install`. `uv sync` is 3-5x faster:

```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v5
  with:
    version: "latest"

- name: Install dependencies
  run: uv sync
```

### 4. Remove unused backend install from Build workflow (saves **~35s**)

`nextjs.yml` installs backend deps but runs no backend tests or lint. Either:
- **Remove** the `Setup Python` and `Install backend dependencies` steps entirely
- **Or** add backend unit tests / pylint to justify the install

### 5. Add concurrency groups (saves **queued minutes**)

The Build workflow has no concurrency group. Rapid pushes queue redundant runs:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

The Playwright workflow also lacks a concurrency group.

### 6. Add npm cache (saves **~3-5s/shard**)

Neither workflow caches npm. Add to `setup-node`:

```yaml
- uses: actions/setup-node@v4
  with:
    node-version: 24
    cache: 'npm'
    cache-dependency-path: |
      package-lock.json
      app/package-lock.json
```

### 7. Docker build caching for releases (saves **~2-5 min** on releases)

No layer caching on the Docker build. Add:

```yaml
- uses: docker/build-push-action@v5
  with:
    context: .
    file: ./Dockerfile
    push: true
    tags: ${{ env.TAGS }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### 8. Deduplicate npm installs in Playwright workflow

The Playwright workflow runs `npm ci` twice — once for frontend (`./app`) and once for root (Playwright). These could be consolidated or at least cached.

---

## Summary

| # | Optimization | Time saved | Effort |
|---|---|---|---|
| 1 | Cache/pre-seed FalkorDB data | **~7 min** | Medium |
| 2 | Cache Playwright browsers | **~1.5 min** | Low |
| 3 | Switch to `uv` from `pip` | **~40s** | Low |
| 4 | Remove unused backend install from Build | **~35s** | Trivial |
| 5 | Add concurrency groups | Variable | Trivial |
| 6 | Add npm cache | ~10s | Trivial |
| 7 | Docker layer caching | ~2-5 min (releases) | Low |
| 8 | Deduplicate npm installs | ~5s | Low |

**Total potential savings: ~9-10 min per CI run**, bringing Playwright from ~10 min/shard down to ~4-5 min/shard (dominated by the actual test execution).

The single biggest win is **pre-seeding FalkorDB data** — it alone accounts for 37% of the Playwright workflow runtime.
