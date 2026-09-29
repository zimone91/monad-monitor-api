# Rate limits

Every public route is rate-limited per client IP address, in fixed 60-second windows.

## Classes

| Class | Requests per 60 s | Routes |
|---|---|---|
| `heavy` | 120 | `GET /validators`, `GET /validator/{id}`, `GET /validator/{id}/score`, `GET /validator/{id}/slots`, `GET /validator/{id}/series`, `GET /validator/{id}/delegators`, `GET /network/decentralization` |
| `standard` | 300 | `GET /validator/{id}/events`, `GET /health`, `GET /health/indexer`, `GET /openapi.json`, unknown paths |
| `logo` | 600 | `GET /validator/{id}/logo` |

## How requests are counted

- Each class has one budget per client address, shared by all routes in the class.
- A route draws from the same budget with or without the `/v1` prefix.
- `HEAD` counts like `GET`. CORS preflight requests (`OPTIONS`) are not counted.
- Error responses count too.
- A window opens with the first counted request and lasts 60 seconds.
- `api.zim.one` has no IPv6 address (checked 2026-09-25), so clients are counted per IPv4 address. Clients behind one NAT address share a budget.
- A request over budget is refused before the API does any work for it.

## Headers

Header names are case-insensitive; over HTTP/2 they arrive in lowercase.

| Header | Sent with | Value |
|---|---|---|
| `RateLimit-Limit` | Every response of a limited route | The class budget |
| `RateLimit-Remaining` | Every response of a limited route | Requests left in the current window |
| `RateLimit-Reset` | Every response of a limited route | Seconds until the window ends |
| `Retry-After` | `429` only | Seconds to wait before the next request in that class |

All four are named in `Access-Control-Expose-Headers`, so a script running in a browser can read them cross-origin.
Without that header the browser hides every response header but a short safelist, and `fetch` would see the `429` status with no budget to pace against.

```sh
curl -s -D - -o /dev/null -H 'Origin: https://example.com' https://api.zim.one/v1/health \
  | grep -i '^access-control-expose-headers'
```

## A 429 response

Shape, with the headers that matter:

```text
HTTP/2 429
cache-control: no-store
ratelimit-limit: 120
ratelimit-remaining: 0
ratelimit-reset: 37
retry-after: 37

{"error":"rate limit exceeded","limitClass":"heavy","retryAfterSec":37,"time":"…"}
```

## Backing off

1. Wait `Retry-After` seconds before the next request in that class.
2. If another `429` follows, double the wait each time and add random jitter.
3. Pace requests by `RateLimit-Remaining` and `RateLimit-Reset` instead of waiting for a `429`.
4. Cache on your side. Data routes send `Cache-Control: public, max-age=60`. The indexer runs every 5 minutes, and the score, network concentration and delegator lists are recomputed at most every 10 minutes.

## Check your budget without a burst

```sh
curl -s -D - -o /dev/null https://api.zim.one/v1/validators | grep -i '^ratelimit-'
curl -s -D - -o /dev/null https://api.zim.one/v1/validator/109/score | grep -i '^ratelimit-'
```

Both routes are `heavy`, so the second `RateLimit-Remaining` is one lower than the first, unless the window ended in between.
