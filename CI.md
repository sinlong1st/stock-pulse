# Continuous Integration with GitHub Actions — an explainer

Right now, StockPulse's ~363 tests only run when someone remembers to type
`pytest`. That someone is usually an AI assistant, and twice in a single session
a change broke existing tests that only got caught because we happened to run
them. **Continuous Integration (CI)** is the fix: a robot that runs your checks
automatically, every time you push code.

This doc explains what that means, what GitHub Actions actually *is*, and what a
workflow for this project would look like — line by line. No prior CI experience
assumed.

---

## 1. The problem CI solves

Here's the failure mode. You (or an assistant) change something in
`app/evaluation.py`. It looks right. You commit, push, deploy to the droplet.
Three days later you notice the Evaluation screen is empty, and it takes an hour
to work out that a function signature changed and a caller was never updated.

The test that would have caught it existed the whole time. Nobody ran it.

CI removes the "nobody ran it" step. Push code → a fresh computer somewhere runs
your tests → you get a green tick or a red cross within a couple of minutes.
That's the entire idea. Everything else is detail.

> **"Continuous Integration" is a slightly grand name** for "run the checks
> automatically". The term comes from a time when teams integrated their work
> once a month and it was agony. Running tests on every push was the cure.

---

## 2. What GitHub Actions actually is

GitHub Actions is GitHub's built-in robot. Three things to understand:

**A runner** is a temporary computer GitHub rents to you for the length of a job.
It boots fresh, does what you tell it, then is destroyed. Nothing persists
between runs. This is a *feature* — it means the tests run on a clean machine,
not one where "it works because I installed something six months ago".

**A workflow** is a YAML file in `.github/workflows/`. GitHub reads it, and any
file it finds there becomes a robot. The filename doesn't matter; the contents do.

**A trigger** is the event that starts it: a push, a pull request, a schedule, a
manual button click.

So a workflow is: *"when X happens, boot a computer, run these commands"*.

### What it costs

**Free for public repositories.** StockPulse's repo is public
(`github.com/sinlong1st/stock-pulse`), so unlimited minutes on standard runners,
no card needed. Private repos get a monthly free allowance (~2,000 minutes) and
bill beyond that. Our run would take ~2 minutes, so even privately this would be
free in practice.

---

## 3. What CI would check in *this* project

Three independent checks, matching what's already run by hand:

| Check | Command | Catches |
|---|---|---|
| **Backend tests** | `pytest` | broken logic, changed signatures, bad SQL |
| **Mobile typecheck** | `npx tsc --noEmit` | wrong types, renamed fields, missing props |
| ~~Backend lint~~ | ~~`ruff check .`~~ | **not wired up** — see [§7](#one-thing-to-deal-with-first) |

> **Status: live.** The workflow is at `.github/workflows/ci.yml` and runs on every
> push to `main`, on pull requests, and on demand. Linting is deliberately left
> out until the existing violations are cleared.

That third one matters more than it sounds. When the backend renamed `lastDate`
→ `quarterEnd`, `tsc` is what proves the app was updated to match. A backend
change that silently breaks the app is exactly the bug CI is best at catching.

### What CI will *not* do here

**It won't deploy.** Deployment stays manual: `git pull && docker compose up -d
--build` on the droplet, then `eas update` for the app. CI that auto-deploys is a
real thing (Continuous *Deployment*), but it's a bigger decision — you'd be
letting a robot push to your live server. Not yet.

**It won't call OpenAI or Yahoo.** Every external service in this project is
mocked in tests. That's deliberate and it's what makes CI viable: the runner has
no API keys, no `.env`, and no network dependencies. If tests started making real
API calls, CI would be flaky *and* expensive.

> This is why "external services mocked in tests" is a project rule, not a style
> preference. It's the thing that makes automated testing possible at all.

---

## 4. The workflow file, line by line

This would live at `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Lint
        run: ruff check .

      - name: Test
        run: pytest -q

  mobile:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: mobile/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Typecheck
        run: npx tsc --noEmit
```

Now the explanation.

### The triggers

```yaml
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
```

- `push: branches: [main]` — run on every push to main. That's your normal flow.
- `pull_request` — run on PRs too. You don't use PRs today, but if you ever do,
  this means a PR page shows a green tick before you merge.
- `workflow_dispatch` — adds a "Run workflow" button in the GitHub UI. Handy for
  re-running after a flaky failure without pushing an empty commit.

### The two jobs

```yaml
jobs:
  backend:
  mobile:
```

Two jobs run **in parallel on separate runners**. Python and Node don't need each
other, so running them together halves the wall-clock time. It also means a
failure message tells you *which half* broke without reading logs.

### `uses:` versus `run:`

```yaml
- uses: actions/checkout@v4
- name: Test
  run: pytest -q
```

`run:` is a shell command — exactly what you'd type locally.

`uses:` pulls in a pre-built **action**, a reusable step someone else wrote.
`actions/checkout@v4` clones your repo onto the runner. **This is not optional
and not automatic** — a fresh runner has no idea what your code is until you
check it out. It's the most common thing beginners forget.

The `@v4` pins a major version, so the action can't change under you tomorrow.

### Caching

```yaml
cache: pip
```

Without this, every run re-downloads FastAPI, SQLAlchemy and friends from
scratch. With it, GitHub keeps the downloaded packages between runs and a ~90
second install drops to ~10. Same for `cache: npm` on the mobile side.

### `npm ci`, not `npm install`

```yaml
- run: npm ci
```

`npm ci` installs **exactly** what `package-lock.json` specifies and errors if
the lockfile is out of sync. `npm install` is allowed to quietly upgrade things.
On a machine that's testing whether your code works, you want the exact versions
you develop against — especially here, where the app is deliberately pinned to
**Expo SDK 54** and an accidental upgrade would be a real problem.

---

## 5. Reading a failed run

When something breaks you'll get an email and a red ✗ next to the commit on
GitHub. Click it → the Actions tab → the failed job → the failed step expands to
show the exact output you'd have seen locally.

The mental model that saves time: **a red CI is not a CI problem.** It is
almost always your code, saying the same thing `pytest` would have said on your
laptop. The runner is just the messenger.

The genuine exceptions, roughly in order of likelihood:

- **A test depends on the local machine.** Ours nearly did — one test reached for
  the real `stockpulse.db`, which exists on your laptop but never on a runner.
  That test now mocks the database. CI is good at surfacing this class of bug,
  because a fresh machine has none of your local state.
- **A test depends on the clock or timezone.** Runners are UTC. The
  `daysUntil` timezone bug found earlier this session is exactly this shape — it
  behaved differently depending on what time of day it ran.
- **A test hits the network.** Shouldn't happen here, by design.

---

## 6. Would this have caught the real bugs?

Honest answer, using this project's actual history:

| Bug | Caught by CI? |
|---|---|
| `run_report` gained `progress=`, test fakes not updated | **Yes** — 9 tests failed |
| `parse_horizon` accepting `5w`, old test expected a raise | **Yes** — immediately |
| `build_evaluation` reaching an unmigrated DB column | **Yes** |
| Backend renamed `lastDate` → `quarterEnd`, app not updated | **Yes** — via `tsc` |
| Long-term support ranking above near-term | **No** — logic was wrong, tests agreed |
| Loader showing a stale strategy name | **No** — no test covered it |
| Vietnamese diacritics clipped in the loader | **No** — visual, untestable here |

So: roughly **four of seven**. CI is excellent at catching *regressions* — things
that used to work — and useless against bugs where the code does exactly what you
told it and what you told it was wrong. That's not a knock; regressions are the
majority of bugs on a project that keeps growing, and they're the ones that waste
the most time because you're not looking for them.

---

## 7. What actually shipped

The live workflow is **tests-only** — the `Lint` step from the example above is
deliberately omitted. Two small deviations from the sample, both intentional:

- **Node 22**, matching the local toolchain rather than the 20 in the example.
- **A `concurrency` block** that cancels a run when a newer push supersedes it.
  Faster feedback, and no point finishing a run for code that's already stale.

Before wiring it up I checked the things that pass locally but fail on a fresh
runner: no test reads a real `.env`, none uses a naive `datetime.now()` that a
UTC runner would shift, none touches the real `stockpulse.db`, and `npm ci`
resolves the lockfile cleanly. Those are the four usual culprits.

### One thing to deal with first

I ran the lint step against the current codebase. It reports **96 errors** —
mostly `E501 Line too long` in tests, 36 of them auto-fixable. The tests all pass;
linting has simply never been enforced, so violations accumulated.

That's why lint isn't in the workflow. Three ways to bring it in when you want to,
best first:

1. **Clean it up, then enforce.** `ruff check --fix .` handles 36 automatically;
   the rest are mostly long lines needing a manual wrap. An hour of tidying, and
   the lint step stays meaningful forever after.
2. **Leave it out** — where we are now. The tests are where the value is.
3. **Warn without failing.** `run: ruff check . || true` — reports problems but
   never fails the build.

**Don't leave CI red on day one.** A build that's always red teaches you to
ignore the red, and then it catches nothing — worse than having no CI, because
you think you're covered. Green-by-default is the whole point: red has to *mean*
something.

---

## Further reading

- [GitHub Actions docs](https://docs.github.com/en/actions) — the official
  reference, genuinely good
- [Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax-for-github-actions)
  — every YAML key explained
- [`actions/setup-python`](https://github.com/actions/setup-python) and
  [`actions/setup-node`](https://github.com/actions/setup-node) — the two setup
  actions used above
