# Deployment

How to build and run the COSMO Data Agent Backend as a Docker container, what must be configured at runtime, and the one open problem (FabriX model credentials) with its possible solutions.

## The big picture

This service is a **custom FastAPI backend** that embeds FabriX ADK agents. It is *not* a standard `fadk` agent workspace: it serves its own REST API (`/auth`, `/apps`, `/health`), owns its session store (Postgres) and artifact storage (S3-compatible object storage), and calls FabriX only for model inference and MCP tools.

Because of that, it deploys like any other containerized service — the same manner as `cosmo-milvus-mcp-server` — **not** through the FabriX `fadk build` / AgentOps flow (see [Why not `fadk build`?](#route-c-fadk-build--agentops-deploy)).

```mermaid
flowchart LR
    FE[Frontend] -->|Bearer token| BE

    subgraph container [Docker container]
        BE[COSMO Data Agent Backend<br/>:9999]
    end

    BE -->|JWKS, token exchange| KC[Fabrix Keycloak]
    BE -->|sessions| PG[(Postgres)]
    BE -->|artifacts| OS[(Object storage)]
    BE -->|tools| MCP1[MongoDB MCP]
    BE -->|tools| MCP2[Milvus MCP]
    BE -.->|"model calls (see Open problem)"| FX[FabriX model API]
```

Everything on the right side must be reachable **from inside the container** — see [Networking](#networking).

## Prerequisites

- Docker on the build/deploy machine, with access to the internal registry (`docker-remote.bart.sec.samsung.net`).
- A pip index that serves `fabrix-adk` (see [requirements_py313_prod.txt](requirements_py313_prod.txt)). The public PyPI does not have it — if the build fails on `fabrix-adk`, apply the same internal pip index configuration your team uses for other FabriX builds.
- Network access from the container to: Fabrix Keycloak (token verification), the session Postgres DB, the object storage endpoint, both MCP servers, and the FabriX model API.

## Build the image

### Deploy folder layout

Same layout as the milvus MCP server deployment: a folder containing the repository checkout, the production `config.yaml`, and the Docker files copied up from the repo.

```
deploy/
├── Dockerfile          # copied from da-backend/Dockerfile
├── .dockerignore       # copied from da-backend/.dockerignore  (must sit at context root!)
├── config.yaml         # production config — see Configuration below
└── da-backend/         # this repository
```

> `.dockerignore` is only honored at the **root of the build context**. If it stays inside `da-backend/`, the local `venv/` and `.git/` get copied into the image and bloat it by hundreds of MB.

### Dockerfile

The [Dockerfile](Dockerfile) is versioned in this repo:

```dockerfile
FROM docker-remote.bart.sec.samsung.net/python:3.13.13

COPY ./da-backend /home/work/da-backend
COPY ./config.yaml /home/work/da-backend/config.yaml

WORKDIR /home/work/da-backend
RUN python -m pip install -r requirements_py313_prod.txt --no-cache-dir

EXPOSE 9999

CMD ["python", "-m", "data_agent", "-c", "/home/work/da-backend/config.yaml"]
```

The entry point is `python -m data_agent`; the `-c` flag is parsed by `load_config()` in [common/config.py](common/config.py), exactly like `python -m milvus_mcp -c ...`.

### Build

From the `deploy/` folder:

```bash
docker build -t cosmo-data-agent .
```

## Configuration

Configuration is loaded in two layers, later wins:

1. The `config.yaml` passed via `-c` (baked into the image at build time).
2. **Environment variables** (`docker run -e ...`), which override individual keys at container start.

### Rule: no secrets in the image

Anything `COPY`-ed into the image lives in a layer forever — even if a later layer overwrites the file, `docker history`/`docker save` can recover it. Therefore:

- The production `config.yaml` in the deploy folder must contain **no credentials** (no object-storage keys).
- Secrets are injected at runtime via environment variables.
- The repo's own [config.yaml](config.yaml) (development values) is copied in by `COPY ./da-backend` before being overwritten — keep development secrets out of it too, or add `da-backend/config.yaml` to the deploy folder's `.dockerignore`.

### Environment variable reference

Every variable maps to a `config.yaml` key (see `_ENV_MAP` in [common/config.py](common/config.py)):

| Variable | Config key | Notes |
|---|---|---|
| `SERVER_PORT` | `server_port` | Default in config: `9999` |
| `LAB_ID` | `lab_id` | FabriX Lab ID |
| `TENANT_CODE` | `tenant_code` | FabriX tenant |
| `BASE_URL` | `base_url` | FabriX platform base URL |
| `OTEL_ENABLED` | `otel_enabled` | `"true"` / `"false"` |
| `LOG_LEVEL` | `log_level` | e.g. `INFO` |
| `MONGODB_MCP_HOST` / `MONGODB_MCP_PORT` | `mongodb_mcp.*` | **Must not be `localhost`** — see Networking |
| `MILVUS_MCP_HOST` / `MILVUS_MCP_PORT` | `milvus_mcp.*` | **Must not be `localhost`** — see Networking |
| `AUTH_ENABLED` | `auth.enabled` | Keep `true` in production; `false` is a local-dev stub |
| `AUTH_ISSUER` | `auth.issuer` | Fabrix Keycloak realm URL |
| `AUTH_CLIENT_ID` | `auth.client_id` | `fabrix-adk` |
| `AUTH_REDIRECT_URI` | `auth.redirect_uri` | **Always set explicitly, and it must be registered on the Keycloak client** — see [The redirect URI is not yours to choose](#the-redirect-uri-is-not-yours-to-choose). Empty means "derive from the incoming request URL", which is wrong behind TLS-terminating proxies |
| `AUTH_FRONTEND_URL` | `auth.frontend_url` | Frontend origin that `/auth/callback` 302-redirects to with the tokens in the URL fragment (e.g. `https://app.example`); empty falls back to JSON in the tab |
| `SESSION_DB_HOST` / `SESSION_DB_PORT` / `SESSION_DB_NAME` | `session_db.*` | Postgres session store |
| `OBJECT_STORAGE_BUCKET` / `OBJECT_STORAGE_ENDPOINT` | `object_storage.*` | |
| `OBJECT_STORAGE_ACCESS_KEY` / `OBJECT_STORAGE_SECRET_KEY` | `object_storage.*` | **Secrets — env vars only, never in the image** |

### Networking

Inside a container, `localhost` is the container itself. The development config points both MCP servers at `localhost` — in production these must be the real service hostnames (or Docker network aliases / compose service names). The same applies to the Postgres host and object storage endpoint.

### The redirect URI is not yours to choose

Keycloak redirects only to URIs registered on the `fabrix-adk` client, and that list belongs to the FabriX platform team. The only loopback URI known to be registered is the `fadk` CLI's hardcoded default (`fabrix/common/auth/pkce_storage.py`):

```python
_DEFAULT_KEYCLOAK_REDIRECT_URI = "http://localhost:53862/callback"
```

Local dev borrows it by running the backend on port 53862 (see [AUTHENTICATION.md](AUTHENTICATION.md)). **That does not survive containerization** — a deployed backend is not on the user's `localhost`. Note what does and does not depend on registration:

| Capability | Needs a registered redirect URI? |
|---|---|
| Verifying bearer tokens (`/auth/me`, all `/apps/...`) | **No** — JWKS is public, verification is local |
| `POST /auth/refresh` | **No** — no browser redirect involved |
| `GET /auth/login` → `GET /auth/callback` | **Yes** — Keycloak refuses unregistered URIs |

So a container can serve the whole authenticated API from day one; only the browser sign-in leg is blocked. Three ways to unblock it, best first:

1. **Request a dedicated Keycloak client** for this backend, with this environment's callback URL as its valid redirect URI. Cleanest: independent of the CLI's client, and per-environment URIs can be added without touching `fabrix-adk`.
2. **Ask for this environment's URL to be added to `fabrix-adk`.** Faster, but it is a shared CLI client — the platform team may reasonably decline.
3. **Skip the backend's browser leg entirely.** The backend is a resource server; if the frontend obtains a Fabrix token by other means, `/auth/login` is never called and nothing else changes.

Whichever route: the URI given to the platform team must be **byte-identical** to `AUTH_REDIRECT_URI`, including scheme, host, port, and trailing-slash form — Keycloak matching is exact, and the same string is replayed at token exchange ([auth.py](data_agent/routers/auth.py)). Register the `/auth/callback` path; the unprefixed `/callback` alias exists only for the CLI-registered dev URI.

Until one of these lands, deploy with `AUTH_REDIRECT_URI` set anyway and treat `/auth/login` as known-broken in that environment.

#### What to send the platform team

Nothing in this repository can add a redirect URI — the list lives in the Keycloak admin console for the `fabrix` realm. Fill in the two hostnames and send:

> **Subject: Keycloak client for COSMO Data Agent Backend**
>
> We run a backend service (custom FastAPI, deployed as a container) that signs users in against the `fabrix` realm with OpenID Connect Authorization Code + PKCE (S256), exactly like `fadk login`. The resulting access tokens are also the bearer tokens for our own REST API, which verifies them locally against the realm JWKS.
>
> We would like a **dedicated public client** for this service rather than reusing `fabrix-adk`:
>
> - Realm: `fabrix`
> - Client ID: `cosmo-data-agent` (or whatever naming you prefer)
> - Client type: **public** (no client secret), Standard Flow enabled, PKCE required, method `S256`
> - Valid redirect URI: `https://<backend-host>/auth/callback`
> - Web origins: `https://<frontend-host>`
> - Scopes: `openid profile email`
>
> If policy requires a confidential client with a secret instead, please say so — we will add secret handling on our side.
>
> If a dedicated client is not possible, the fallback ask is to add `https://<backend-host>/auth/callback` to the existing `fabrix-adk` client's valid redirect URIs.

When they reply:

- New `client_id` → set `AUTH_CLIENT_ID` alongside `AUTH_REDIRECT_URI`.
- **Confidential client (a secret was issued)** → this needs a code change first: [auth_service.py](data_agent/services/auth_service.py) sends `client_id` only, with no `client_secret`, on both the token exchange and the refresh call. Keycloak rejects a confidential client without one.

Quick way to check whether a URI is registered, before deploying anything: open

```
https://genai.sec.samsung.net/iam-keycloak/realms/fabrix/protocol/openid-connect/auth?response_type=code&client_id=<client>&redirect_uri=<url-encoded-uri>&scope=openid+profile+email&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
```

in a browser. A sign-in page (or an instant redirect) means it is registered; a Keycloak *"Invalid parameter: redirect_uri"* page means it is not.

### Login state is in-process — do not scale the login leg

The PKCE `code_verifier` is held in a dict in `AuthService` ([data_agent/services/auth_service.py](data_agent/services/auth_service.py)), so `/auth/login` and the matching `/auth/callback` **must hit the same process**. Consequences:

- Run **one uvicorn worker** (the current entry point does; do not add `--workers`).
- With more than one replica, either keep sign-in on a single instance or enable sticky sessions at the load balancer — otherwise logins fail intermittently with `login_expired`.
- Any restart (including rolling deploys) drops in-flight logins; users retry and succeed. Harmless, but it explains sporadic `login_expired` right after a deploy.

Moving this state to a signed cookie or Redis removes the constraint and is the prerequisite for scaling out.

## Run

```bash
docker run -d --name cosmo-data-agent \
  -p 9999:9999 \
  -e MONGODB_MCP_HOST=mongodb-mcp.internal \
  -e MILVUS_MCP_HOST=milvus-mcp.internal \
  -e SESSION_DB_HOST=10.240.35.173 \
  -e OBJECT_STORAGE_ACCESS_KEY=... \
  -e OBJECT_STORAGE_SECRET_KEY=... \
  -e AUTH_REDIRECT_URI=https://<public-host>/auth/callback \
  -e AUTH_FRONTEND_URL=https://<frontend-host> \
  cosmo-data-agent
```

Verify:

```bash
curl http://<host>:9999/health        # liveness — no auth required
docker logs -f cosmo-data-agent       # startup log: "Starting COSMO Data Agent Backend"
```

> **`/health` green does not mean model calls work.** The server boots without any FabriX credential and only fails on the first model call — see the open problem below. Include one real agent request in the smoke test.

## Open problem: FabriX model credentials

**This is the one thing the Dockerfile does not solve.**

Every agent calls `build_model(...)` from `fabrix-adk`. On a development machine, fabrix-adk authenticates using the credential that `fadk login` writes to the user's home directory (`auth.json`). A fresh container has never run `fadk login`, so:

- the container **starts fine** and `/health` responds,
- the **first model call fails** with an authentication error.

**What does *not* work:** mounting a host's `auth.json` into the container. Fabrix refresh tokens are session-bound (roughly 4 hours idle) and are not renewed without an interactive login — the container would die quietly a few hours after every login.

Three viable routes, in order of fit:

### Route A (recommended): per-user token pass-through

The backend already authenticates every request against the **same Keycloak realm and client** that `fadk login` uses (see [AUTHENTICATION.md](AUTHENTICATION.md)). That means every incoming request carries a valid Fabrix access token of the actual user — and the seam for reusing it is already built:

- `get_current_user` in [data_agent/dependencies.py](data_agent/dependencies.py) sets the `current_fabrix_token` contextvar per request.
- Nothing reads that contextvar yet; model calls still fall back to the server-wide `auth.json`.

Remaining work:

1. Inspect `fabrix/adk/models.py` in site-packages (work machine) to find where `build_model` attaches credentials to the model HTTP call.
2. Override that attachment point to read `current_fabrix_token` first, falling back to the default behavior when it is unset (background/system tasks).

Why this is the best fit: the container then needs **zero server-side FabriX credentials** — credentials arrive with each request, token refresh is the client's job (`/auth/refresh`), and model usage is metered against the real user instead of one shared identity.

Caveat: server-initiated work with no request context (e.g. system/title generation runs) still needs *some* credential — either keep those on Route B, or run them with the requesting user's token while it is valid.

### Route B: service credentials via environment variables

The FabriX documentation has an "Environment Variables — Agent .env and runtime environment variables" section. **Ask the FabriX platform team** whether fabrix-adk supports a non-interactive service credential (service account / client-credentials grant) configured via env vars. If yes, the container works as-is with a couple of extra `-e` values and no code change. Cheapest solution *if* it exists.

### Route C: `fadk build` / AgentOps deploy

The FabriX-sanctioned deployment: the platform builds the image, deploys it into the FabriX runtime, and **injects credentials itself**. Not a fit for this backend as it stands:

- `fadk build` packages a standard agent *workspace* (`agent.py` exporting the runtime app + `agent.yaml` metadata) and serves it behind the **platform's API surface**.
- This repo is a custom FastAPI application — its own routers, session DB, object storage, and auth flow. Deploying via `fadk build` would deploy the agent part only; the REST API the frontend depends on would not exist there.

Choose this route only if you are willing to restructure into a standard workspace and move serving into the FabriX platform.

## Pre-deployment checklist

- [ ] Image builds cleanly (internal pip index resolves `fabrix-adk`).
- [ ] Production `config.yaml` contains no secrets; secrets injected via `docker run -e`.
- [ ] MCP hosts, Postgres host, and object storage endpoint are reachable from inside the container (not `localhost`).
- [ ] `AUTH_REDIRECT_URI` set explicitly (never left at the dev value `http://localhost:53862/callback`).
- [ ] That exact URI is **registered on the Keycloak client** by the FabriX platform team — or `/auth/login` is accepted as non-functional in this environment.
- [ ] Single worker, and sign-in traffic not spread across replicas without sticky sessions.
- [ ] `AUTH_FRONTEND_URL` points at this environment's frontend origin.
- [ ] `/health` responds after start.
- [ ] **One real agent request succeeds** (proves model credentials — see the open problem).
- [ ] Model credential route decided: A (token pass-through), B (service credential), or C (platform deploy).
