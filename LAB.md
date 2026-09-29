# Lab: put the model behind a URL

The triage step has been a function call in your own process. Tonight it goes behind a
URL, on a serverless function in your Learner Lab, and you measure what changed. Write
down three numbers by the end: **cold start**, **warm latency at the 95th percentile**,
and **what a time limit below the model's latency does**.

**What this lab shows.**

1. **The boundary moved; the measurement did not.** The same golden set, the same scorers,
   the same numbers, with the model call on another machine.
2. **A cold start is real, and it is import time.** The first call into a new sandbox pays
   for loading the runtime and the SDK. You can see it, and you can force it.
3. **A time limit is process death.** A call that is still waiting on the model when the
   limit hits does not fail gracefully. It stops. The record you keep of it is a design
   decision.
4. **The key moved too.** The Gemini key is in the function's environment. The laptop
   that calls the URL never holds it.

## Part 0: the arithmetic, before anything is deployed

On paper, for a system at **one million tickets a month**, one model call per ticket,
about 3,000 tokens in and 200 out:

| | your number |
|---|---|
| tickets per second, average | |
| tickets per second, a busy hour at 5× | |
| tokens per month, in and out | |
| cost per month on a small model (≈ \$0.10 in, \$0.40 out per million tokens) | |
| the quota you would need, in requests per minute, to keep up with the busy hour | |
| seconds a customer would wait if the model call were inside the request | |

Keep it; the lab's last question comes back to it.

## Part 1: run it here first

```bash
uv run src/function/handler.py
```

That is the deployed function, exercised the way Lambda will call it, with the fake
provider and no AWS. Read `src/function/app.py` while it runs. It is one page: a FastAPI app
with one endpoint that checks a token, reads the ticket and the account from the request,
calls `triage()` exactly as `record.py` does, and returns the record plus what only the
function can know: whether this was a cold start, how long importing everything took, how
long the function itself took. `handler.py` is the three lines that adapt the app to
Lambda's event shape.

Now serve it on a local URL, with Swagger, and call it the way you will call the real one:

```bash
PROVIDER=fake uv run src/function/local_server.py              # terminal 1: http://127.0.0.1:9000/docs
uv run record.py --provider http --url http://127.0.0.1:9000/triage --name local-url --runs 1   # terminal 2
uv run score.py local-url
```

Open http://127.0.0.1:9000/docs, expand **POST /triage**, and send the example request
from the browser: the same call `record.py` makes, one at a time. No token is needed
locally; only the deployed function checks one. Same harness, same
report, the model call one HTTP hop away. Stop the server when you are done (Ctrl-C).
With your key in `.env` and no `PROVIDER=fake`, the same server calls the real model. Then record the real baseline in this process, with your key, so
there is something to compare against:

```bash
uv run record.py --runs 1          # 10 calls, in this process → data/fixtures/local/
```

## Part 2: deploy it

Start a Learner Lab session, paste the CLI credentials into `~/.aws/credentials`, then:

```bash
./deploy.sh
```

Read what it prints. It installs the dependencies **for Lambda's Linux, not your laptop**,
zips them with `src/`, creates the function under the lab's
pre-made role with a 30-second time limit and 512 MB, gives it a URL, and saves the URL
and a shared token to `.env`. About a minute. Then:

```bash
./call.sh src/function/sample-event-body.json
```

A decision, from a machine that is not yours, with your Gemini key on it and not in the
request. The URL is not public: the Learner Lab refuses anonymous function URLs, so every
call is signed with the same AWS session credentials `deploy.sh` used (`call.sh` and
`record.py` do the signing). The `x-lab-token` header is a second lock of your own.

## Part 3: call it, and score it

```bash
uv run record.py --provider http --runs 3     # 30 calls over the URL → data/fixtures/http/
uv run score.py local http
```

The report compares the in-process baseline with the deployed function, slice by slice.
Expect **no change** or **cannot tell** on every slice: the same model, the same prompt,
the same distribution of outputs, a different machine. The harness did not notice the
move. That is the point: it can gate any placement.

## Part 4: measure it

```bash
uv run latency.py http
```

Per run: the cold start, if the run had one, broken into import time, the model's own
latency, and the rest (network, the runtime); the warm calls' round trip at the median and
the 95th percentile, beside the model's own latency; and any errors.

If no run shows a cold start, the sandbox was already warm from your curl. Force one:

```bash
./deploy.sh --recycle                          # replaces every warm sandbox
uv run record.py --provider http --name http-cold --runs 1
uv run latency.py http-cold
```

Write down the three numbers so far: **cold start**, and **warm p50 and p95** of the round
trip. Then answer: of a warm round trip, how much is the model and how much is everything
else? Which of the two would a bigger function, or a closer region, change?

## Part 5: kill it

The function's time limit is a number you set; the platform enforces it by killing the
sandbox mid-call. The model's own latency here is under a second warm, so set the limit
**below** it and record:

```bash
./deploy.sh --timeout 1
uv run record.py --provider http --name http-1s --runs 1
uv run latency.py http-1s
uv run score.py http http-1s
```

Every call comes back as `error`, and not after one second: the platform killed the
function at one second, and the URL layer took another second or so to tell you. Look at
one record in `data/fixtures/http-1s/run-1.jsonl`: what is in it, and what is not? The model
may well have answered into the void; the money it proposed is nowhere.

Now set the limit from your measurement instead of from a default: take the warm p95
from Part 4, round it up to whole seconds, and add one.

```bash
./deploy.sh --timeout 2          # or whatever your p95 said
uv run record.py --provider http --name http-p95 --runs 1
uv run latency.py http-p95
```

Most calls survive; the ones that do not are the tail. That is what a time limit is for:
a decision about how much of the tail you will pay for, made from a number you measured.

Then the design question, in two sentences: **what should a system record for a call
that died at the time limit, and what should it do next?** "Retry" is a fine start; say
what a retry costs when the call had a consequence.

Restore the limit before you leave, or remove the function:

```bash
./deploy.sh                    # back to 30 s
./teardown.sh                  # or remove it; idle it costs nothing either way
```

## Keep

- the three numbers: cold start, warm p95, and the error rate at a 1-second limit
- your Part 0 sheet, with one line added: at the busy hour, would this function's quota
  and its cold starts have mattered?
- the repository, with its fixtures

## If something breaks

| Symptom | What it is |
|---|---|
| `aws sts get-caller-identity failed` | No session, or the pasted credentials expired. Start a session and paste again. |
| `AccessDenied` on `create-function` | The role name is not `LabRole` in your account. Run `aws iam list-roles --query 'Roles[].RoleName'` and set `ROLE` in `deploy.sh`. |
| `Runtime.ImportModuleError` in the response | A dependency was installed for the wrong platform. `rm -rf build` and run `./deploy.sh` again; it must be built with the `--python-platform` flag, which the script sets. |
| `HTTP 401` from `record.py` | The token in `.env` does not match the function's. `./deploy.sh` again; it re-sets both. |
| `HTTP 403` on every call | The request was not signed, or the session credentials behind the signature expired. Start a session, paste credentials, run again. A plain `curl` without `--aws-sigv4` always gets 403 here. |
| `HTTP 502` or `503` on every call | The function is crashing before it answers. `aws logs tail /aws/lambda/triage-url --since 10m` shows the traceback. |
| `rate limited; sleeping` inside the function | Normal on the free tier; the function waits, so the round trip grows. With a short time limit it will die instead. |
| The zip is over 50 MB | Something extra got into `build/pkg`. It should be about 10 MB zipped. |
