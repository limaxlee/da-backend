# Session titles and concurrent session writes

Why a prompt could fail with a 500 while its session was being titled, what changed in the
backend to fix it, and **what the frontend has to change**.

Frontend team: the two sections you need are [What the frontend must
change](#what-the-frontend-must-change) and [API reference](#api-reference). The rest is
background.

---

## The bug

A user creates a session and sends the first prompt. While the agent is running, the
frontend's 5-second session-list poll notices the session has no title and calls
`POST .../title`. A few seconds later **the prompt fails with a 500** and the answer is lost.

From a real log (times are `mm:ss`):

| Time | What happened |
|---|---|
| `41:56` | session created, `POST /run` starts |
| `41:59` | poll → `POST /title` → **400** "session has no user message" |
| `42:04`, `42:09`, `42:14` | three more polls → three more `POST /title`, each starting its own model call |
| `42:15` | one title write **succeeds** |
| `42:17` | a second title write fails — "session has been modified in storage" |
| `42:21` | **the agent run dies** with the same error → `POST /run` returns 500 |
| `42:25` | a third title write fails the same way |

Five model calls, one useful title, and a lost answer.

## Why it happened

Sessions are stored by Google ADK's `DatabaseSessionService`. Its `append_event` uses
**optimistic concurrency**: it compares the `last_update_time` of the in-memory `Session`
object you hand it against the row in Postgres, and *refuses the write* if the row has moved
on since that object was loaded. There is no reload-and-merge — it raises.

Two code paths each held a `Session` snapshot across a multi-second model call, then wrote:

| Writer | Loads the session | Writes | Holds the snapshot for |
|---|---|---|---|
| `POST /run` | ADK's `Runner` at the start of the invocation | on **every** agent event | the whole run — 25 s in the log |
| `POST /title` | `DBSessionService.create_session_title` | once, at the end | ~16 s (the title model call sat in between) |

Whoever wrote second lost. In the log the title won and the run lost — so a **cosmetic title
write killed the user's actual request.** Which one dies is pure timing; it could have gone
the other way.

Two things made it much worse:

1. **Title creation was neither single-flight nor idempotent.** Poll every 5 s × a 16 s model
   call = 3–4 title generations running at once for the same session, each with its own stale
   snapshot, all fighting each other and each costing a model call.
2. **"Not ready yet" was treated as a hard error.** A title request that arrived before the
   user's first message had reached storage raised, logged a full stack trace, and returned
   `400` — even though the correct answer is simply "try again in a moment".

---

## What changed in the backend

The invariant now enforced: **nothing may write a session row while a run is in flight on it,
and nobody holds a session snapshot across an await they do not control.**

### 1. A per-session write guard

New `SessionGuard` (`data_agent/services/session_guard.py`) — one `asyncio.Lock` per session
id, shared process-wide via `get_session_guard()`.

- `POST /run` holds it for the **entire** run.
- Title and rename writes take it only around their own append.
- `is_busy(session_id)` lets the title endpoint bail out early instead of blocking.

### 2. The backend titles sessions itself, after the run

`AgentRunner.run` now schedules `DBSessionService.ensure_session_title` as a **background
task** once the run has released the guard. The title is written when nothing else is holding
the session, so it cannot collide. The client just sees the title appear on its next poll.

This does **not** delay the `/run` response — it is fire-and-forget after the answer is returned.

### 3. Title creation is idempotent and cheap to repeat

`POST /title` now:

- returns the **stored** title if the session already has one, without calling the model;
- returns `409` if a run is holding the session — no model call, no write;
- returns `409` if the session has no user message yet;
- re-checks for an existing title *after* the model call and **drops its own write** if another
  writer won the race in the meantime.

### 4. Writes reload immediately before appending, and retry

Every state write now loads the session one round trip before `append_event` instead of before
the model call, and retries up to 3 times on the stale-session error. This shrinks the
collision window from ~16 s to microseconds and covers writers the in-process guard cannot see.

### 5. Transient states are no longer errors

`SessionBusyError` and `SessionNotReadyError` → **`409` with `Retry-After: 5`**, logged at INFO.
They mean *"ask again shortly"*, not *"something broke"*.

### The same log, replayed on the new code

| Time | What happens now |
|---|---|
| `41:56` | session created, `POST /run` starts and takes the guard |
| `41:59`, `42:04`, `42:09`, `42:14` | polls → `POST /title` → **409**, no model call, no write |
| `42:21` | **the run completes normally and returns the answer** |
| `42:21+` | backend titles the session in the background |
| `42:24` | poll → `POST /title` → **200** with the stored title, no model call |

Five model calls become two. The run cannot be killed.

---

## What the frontend must change

### Required — handle `409` on `POST .../title` as "retry later", not as an error

This is the one breaking change. `POST /apps/users/{user_id}/sessions/{session_id}/title` can
now return **`409 Conflict`** with a `Retry-After: 5` header. It means one of:

- a run is currently in flight for this session, or
- the session's first user message has not reached storage yet.

Both resolve on their own within seconds. A `409` must **not** show an error toast, must not
mark the session as failed, and must not stop the polling loop. Just skip this cycle — the
next poll will get a `200`, or the title will already be there.

```ts
const res = await fetch(`/apps/users/${userId}/sessions/${sessionId}/title`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
})

if (res.status === 409) {
  return // not ready yet; the next poll will pick it up
}
if (!res.ok) {
  // real failure — 400 unknown session, 401 auth, 500 backend
  throw new Error(await res.text())
}
const { session_title } = await res.json()
```

If your fetch wrapper treats every non-2xx as a thrown error and reports it globally, add 409
to its ignore list **for this endpoint**.

### Strongly recommended — stop asking for titles while a run is in flight

The frontend already knows when it has a `POST /run` outstanding for a session. Skip the title
request for that session until the run resolves. This is the single cheapest guard on the
client side, and it avoids a round trip that is now guaranteed to return 409 anyway.

```ts
if (runInFlightBySessionId.has(sessionId)) return
```

### Strongly recommended — never fire two title requests for the same session at once

Today a new title request goes out on every 5 s poll while the session is untitled, even
though the previous one is still running. Keep an in-flight set and skip a session that
already has a title request pending:

```ts
if (titleRequestInFlight.has(sessionId)) return
titleRequestInFlight.add(sessionId)
try { /* ... */ } finally { titleRequestInFlight.delete(sessionId) }
```

The backend now deduplicates these correctly, so this is no longer a correctness issue — but
each redundant request is still a wasted round trip.

### Optional — drop the title trigger entirely

The backend titles every session on its own after the first run. You can remove the poll-driven
`POST .../title` call completely and simply render `state.session_title` from the session list
when it appears (typically within a few seconds of the run finishing).

Keeping the call is fine and now harmless — treat it as a fallback for sessions that somehow
never got titled. If you keep it, all three points above still apply.

### Also affected — `PATCH .../title` (rename)

The rename endpoint can now also return `409`, if a run is still holding the session after the
backend waited 60 s for it. This is rare. Show a "session is busy, try again" message and let
the user retry — do not silently drop the rename, since it is an explicit user action.

### What did **not** change

- The `200` response bodies of every endpoint are unchanged.
- The title still lives at `state.session_title` in the session list and session detail payloads.
- Authentication, the `/run` request and response shapes, and the polling contract are untouched.

---

## API reference

### `POST /apps/users/{user_id}/sessions/{session_id}/title`

Generate and store a title for a session. Safe to call repeatedly.

| Status | Meaning | Frontend action |
|---|---|---|
| `200` | `{"session_title": "..."}` — freshly generated, or the one already stored | Render it |
| `409` | **New.** A run holds the session, or no user message has landed yet. Carries `Retry-After: 5` | **Skip this cycle, no error shown** |
| `400` | The user has no such session | Real error |
| `401` / `403` | Not authenticated / not your session | Real error |
| `500` | Backend failure | Real error |

### `PATCH /apps/users/{user_id}/sessions/{session_id}/title`

Rename a session. `session_title` is passed as a query parameter.

| Status | Meaning | Frontend action |
|---|---|---|
| `200` | Renamed | Done |
| `409` | **New.** The session was still busy after a 60 s wait | Tell the user to retry |
| `400` | The user has no such session | Real error |
| `500` | Backend failure | Real error |

### `POST /apps/users/{user_id}/sessions/{session_id}/run`

Unchanged in shape. It will no longer fail with
`"The session has been modified in storage since it was loaded"`.

### `GET /apps/users/{user_id}/sessions`

Unchanged. `state.session_title` now fills in on its own a few seconds after a run finishes.

---

## Known limitation

The write guard is **per process**. With several uvicorn workers or replicas it will not
serialise writers across them — the reload-and-retry covers the title path, but not a run's
own appends. If the backend is deployed multi-worker, the guard has to become a Postgres
advisory lock (`pg_advisory_xact_lock(hashtext(session_id))`). The `SessionGuard` interface is
small enough to swap in place; this is noted in its docstring.

---

## Files changed

| File | Change |
|---|---|
| `data_agent/services/session_guard.py` | **New.** Per-session write lock |
| `data_agent/services/db_session.py` | Idempotent titling, reload-before-append with retry, guarded writes, `ensure_session_title` |
| `data_agent/services/agent_runner.py` | Holds the guard across the run, schedules titling afterwards |
| `data_agent/routers/session.py` | `409` + `Retry-After` for transient states |
| `data_agent/dependencies.py` | Shared `SessionGuard` singleton |
| `common/constants.py` | `SYSTEM_AUTHOR`, `SESSION_TITLE_KEY` |
| `tests/services/test_session_guard.py` | **New.** Guard behaviour |
| `tests/services/test_db_session.py`, `tests/services/test_agent_runner.py`, `tests/routers/test_session.py`, `tests/routers/conftest.py`, `tests/test_dependencies.py` | Coverage for the races above |
