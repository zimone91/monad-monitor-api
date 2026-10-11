# Errors

Every error body the API sends is JSON and carries `time`.
Every error response the API sends has `Cache-Control: no-store`.

One kind of error does not come from the API.
While the API process cannot be reached, for example for a few seconds during a restart, the proxy in front of it answers by itself, usually with `502 Bad Gateway`.
That body is plain text, the status and its name, with no `time` and no `Cache-Control`.
Treat it as a short outage and retry later.

## Route errors

The body is `{"error":"<reason>", …, "time":"…"}`.

| Status | `error` | Other fields | When |
|---|---|---|---|
| 400 | `invalid validator id` | | `{id}` is not a decimal integer, or is above 9223372036854775807 |
| 400 | `invalid network` | | `network` is a value this API does not know |
| 400 | `invalid time` | `param`: `from` or `to` | `GET /validator/{id}/series`: `from` or `to` cannot be parsed or is out of range |
| 400 | `unsupported network` | `network`, `supported` | `network=testnet`: only `mainnet` is served under `/v1` |
| 404 | `validator not found` | `network`, `validatorId` | `GET /validator/{id}`, `/score` and `/delegators`: the indexer does not know this id. For `/delegators` also when the chain listed no such validator at the first reading |
| 404 | `unknown validator` | | `GET /validator/{id}/slots`: the indexer does not know this id |
| 404 | `no logo` | `network`, `validatorId` | `GET /validator/{id}/logo`: the registry lists no logo |
| 429 | `rate limit exceeded` | `limitClass`, `retryAfterSec` | Over budget; see [rate limits](rate-limits.md) |
| 503 | `delegators unavailable` | `reason`, `retryAfterSec`, `network`, `validatorId` | `GET /validator/{id}/delegators`: no list to give right now; see below |
| 503 | `score unavailable` | `reason`, `retryAfterSec`, `network`, `validatorId` | `GET /validator/{id}/score`: the service has started, and its first score set is not computed yet; see below |
| 503 | `decentralization unavailable` | `reason`, `retryAfterSec`, `network` | `GET /network/decentralization`: the same cause as `score unavailable`; see below |

## `503` from `/delegators`

The delegator list is read from the chain on demand, not from the indexer's tables, and read again once it is 10 minutes old (see [time fields](time-fields.md)).
When there is no list to give, the route answers `503 delegators unavailable`.
The `Retry-After` header and `retryAfterSec` in the body carry the same number of seconds to wait.

| `reason` | Meaning |
|---|---|
| `warming` | The first reading for this validator takes longer than 10 seconds. It keeps running and fills the cache, so a retry after the wait is answered from it. |
| `busy` | Too many readings are queued, so this one was not started. |
| `rpc-failed` | The chain reads failed. |

A `404` from this route means what it says: the indexer does not know the id, or the chain listed no such validator at the first reading. A list once held is not removed when a later reading finds no such validator.

```sh
curl -s -D - -o /dev/null 'https://api.zim.one/v1/validator/109/delegators?limit=1' | grep -iE '^(HTTP|retry-after)'
```

## `503` from `/score` and `/network/decentralization`

The score is computed for the whole set every 10 minutes, behind the set being served.
Only in the first seconds after the service starts is there no set yet: until the first one is computed, both routes answer `503` with `reason: "building"`.
The computation keeps running, so a retry after `Retry-After` seconds is answered from it.

These are not errors:

- `GET /validator/{id}/events` and `GET /validator/{id}/series` answer `200` with an empty list for an id the indexer does not know. `GET /validator/{id}` tells whether an id exists.
- Unknown values of `metric` and `bucket` fall back to the defaults (`production`, `1d`).
- `limit` and `epochs` are clamped: `limit` to 1 to 50 for delegators and 1 to 200 for events, `epochs` to 1 to 200. A value that is not a number falls back to the default.
- Zero is not read the same way everywhere: `limit=0` is 1 for `GET /validator/{id}/delegators` and the default 50 for `GET /validator/{id}/events`, and `epochs=0` is the default of about 7 days. Send the number you want.
- Apart from `/delegators`, no route answers `503`: every data source `/v1` documents is configured, and the routes are served from them or not at all.

## Unknown path

```json
{"message":"Route GET:/v1/example not found","error":"Not Found","statusCode":404,"time":"…"}
```

## Other client errors

Errors raised by the HTTP framework itself keep its shape:
`{"statusCode":400,"error":"Bad Request","message":"…","time":"…"}`.

## Server errors

```json
{"statusCode":500,"error":"Internal Server Error","message":"internal error","errorId":"…","time":"…"}
```

- `errorId` is 16 hexadecimal characters.
- When reporting a problem, quote `errorId` and `time`.
- The message is always `internal error`: a 5xx body carries no internal error text.

Not verifiable from outside: that every 5xx path uses this body, and that the server log keeps the details under `errorId`.

## See one

```sh
curl -s -w '\n%{http_code}\n' https://api.zim.one/v1/validator/12ab
curl -s -w '\n%{http_code}\n' 'https://api.zim.one/v1/validator/109/series?from=yesterday'
```
