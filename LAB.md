# Lab: put the model behind a URL

The triage step has been a function call in your own process. Tonight it goes behind a
URL, on a serverless function in your Learner Lab, and you measure what changed. Write
down three numbers by the end: **cold start**, **warm latency at the 95th percentile**,
and **what a 3-second time limit does**.

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
uv run function/handler.py
```

That is the deployed function, called as a plain Python function with the fake provider.
Read `function/handler.py` while it runs. It is one page: check a token, read the ticket
and the account from the request, call `triage()` exactly as `record.py` does, and return
the record plus what only the function can know: whether this was a cold start, how long
importing everything took, how long the function itself took.

Now serve it on a local URL and call it the way you will call the real one:

```bash
PROVIDER=fake uv run function/local_server.py                  # terminal 1
uv run record.py --provider http --url http://127.0.0.1:9000 --name local-url --runs 1   # terminal 2
uv run score.py local-url
```

Same harness, same report, the model call one HTTP hop away. Stop the server when you
are done (Ctrl-C). Then record the real baseline in this process, with your key, so
there is something to compare against:

```bash
uv run record.py --runs 1          # 10 calls, in this process → fixtures/local/
```

## Part 2: deploy it

Start a Learner Lab session, paste the CLI credentials into `~/.aws/credentials`, then:

```bash
./deploy.sh
```

Read what it prints. It installs the dependencies **for Lambda's Linux, not your laptop**,
zips them with `system/` and the handler, creates the function under the lab's
pre-made role with a 30-second time limit and 512 MB, gives it a URL, and saves the URL
and a shared token to `.env`. About a minute. Then:

```bash
curl -s -X POST "$(grep LAB_URL .env | cut -d= -f2)" \
  -H "x-lab-token: $(grep LAB_TOKEN .env | cut -d= -f2)" \
  -H 'content-type: application/json' -d @function/sample-event-body.json
```

A decision, from a machine that is not yours, with your key on it and not in the request.

## Part 3: call it, and score it

```bash
uv run record.py --provider http --runs 3     # 30 calls over the URL → fixtures/http/
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

Lambda's default time limit is three seconds. A model call takes two to six. Set the
limit to the default and record again:

```bash
./deploy.sh --timeout 3
uv run record.py --provider http --name http-3s --runs 2
uv run latency.py http-3s
uv run score.py http http-3s
```

Some calls come back as `error`. Look at one in `fixtures/http-3s/run-1.jsonl`: what is
in the record, and what is not? The function was killed mid-call; the model may well
have answered into the void; the money it proposed is nowhere.

Then the design question, in two sentences: **what should a system record for a call
that died at the time limit, and what should it do next?** "Retry" is a fine start; say
what a retry costs when the call had a consequence.

Restore the limit before you leave, or leave the function deleted:

```bash
./deploy.sh                    # back to 30 s
./teardown.sh                  # or remove it; idle it costs nothing either way
```

## Keep

- the three numbers: cold start, warm p95, and the error rate at a 3-second limit
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
| `HTTP 502` or `503` on every call | The function is crashing before it answers. `aws logs tail /aws/lambda/triage-url --since 10m` shows the traceback. |
| `rate limited; sleeping` inside the function | Normal on the free tier; the function waits, so the round trip grows. With a 3-second limit it will die instead. |
| The zip is over 50 MB | Something extra got into `build/pkg`. It should be about 10 MB zipped. |
