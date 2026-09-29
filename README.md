# Put the model behind a URL

The support-ticket triage step has been a function call inside your own process. In this
lab it goes behind a URL, on a serverless function in your AWS Academy Learner Lab, and you
measure what changed. Three numbers at the end: **cold start**, **warm latency at the
95th percentile**, and **what the platform's time limit does** to a call that is waiting
on a model.

The system under test is unchanged: `system/triage.py` is the same frozen file as in the
project repository, and the harness scores its outputs the same way. Only where it runs
moves.

| | |
|---|---|
| **In class** | [LAB.md](LAB.md) — *put the model behind a URL* |
| **The function** | [function/handler.py](function/handler.py) — the whole thing, one page |
| **The golden set** | [golden/README.md](golden/README.md) |

## What you need

- Python 3.12 or newer, and [`uv`](https://docs.astral.sh/uv/).
- Your Gemini key, in `.env`.
- The AWS CLI (`brew install awscli`, or see *Configuring AWS* in the course guide), and a
  **running Learner Lab session** with its credentials pasted into `~/.aws/credentials`.
  Sessions last about four hours; the function you deploy outlives them.

Parts 0 and 1 need none of the AWS items. If AWS is not working for you tonight, do
those, then use a partner's URL for the rest.

## Setup, once

```bash
git clone https://github.com/aise-stthomas/put-the-model-behind-a-url
cd put-the-model-behind-a-url
cp .env.example .env         # paste your Gemini key
uv sync
uv run function/handler.py   # the function, called as a plain function, with the fake provider
```

If that printed a decision and a `"function"` block with `"cold_start": true`, you are set.

## The loop

```bash
./deploy.sh                                 # build the package, deploy, print the URL (saved to .env)
uv run record.py --provider http --runs 3   # call the URL over the golden set; fixtures/http/
uv run score.py local http                  # the same scorers as the project: nothing changed
uv run latency.py http                      # cold start · warm p50 and p95 · errors
```

`record.py` writes one line per call as it lands and never repeats a call it already has,
so a rerun continues where it stopped. Over HTTP every record carries two clocks: the
model's own latency, measured inside the function, and the whole round trip, measured
from your laptop.

## The files

```
function/
  handler.py          the function: token check → triage() → the record, plus cold-start and timing metadata
  local_server.py     serves handler.py on http://127.0.0.1:9000, for testing the HTTP path with no AWS
  sample-event.json   what a function URL delivers to the handler; handler.py uses it when run directly
deploy.sh             builds the zip for Lambda's Linux, creates or updates the function, sets the URL
teardown.sh           deletes the function and its URL
record.py             CLI: run the suite, in this process or over HTTP; saves every call
score.py              CLI: reads the fixtures and reports, per slice; never calls a model
latency.py            CLI: the three numbers, per run, from the fixtures
system/               the system under test, frozen. Deployed as-is.
harness/              golden set loader, fixtures, scorers, the report
golden/               the ten tickets and their accounts
fixtures/             every recorded call, by condition and run. Committed.
```

## What this is one instance of

A serverless function with a URL is one placement for a model call: **asynchronous
capacity you rent by the millisecond**, with a cold start when a sandbox is new and a hard
time limit when it runs long. The vendor, the runtime and the CLI flags are September 2026
details. What does not change: the harness does not care where the model runs, so it can
gate any placement; a cold start is import time you pay on the first call and can measure;
and a platform's time limit is process death, which is why every call is recorded as it
lands and why anything longer than one call has to keep its state somewhere that survives.
