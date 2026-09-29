# Monad Monitor API

Independent project by ZIM.ONE, not affiliated with the Monad Foundation.

I built this for my own validator work and decided to share it.
Beta, no SLA.

[![ci](https://github.com/zimone91/monad-monitor-api/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zimone91/monad-monitor-api/actions/workflows/ci.yml)
[![contract](https://img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/contract.json)](https://zimone91.github.io/monad-monitor-api/)
[![data](https://img.shields.io/badge/dynamic/json?url=https://api.zim.one/v1/health/indexer&query=$.status&label=data)](https://api.zim.one/v1/health/indexer)
[![scorecard](https://api.scorecard.dev/projects/github.com/zimone91/monad-monitor-api/badge)](https://scorecard.dev/viewer/?uri=github.com/zimone91/monad-monitor-api)

[![checks](https://img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/checks.json)](https://github.com/zimone91/monad-monitor-api/actions)
[![OpenAPI](https://img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/openapi.json)](openapi/openapi.yaml)
[![status](https://img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/status.json)](CHANGELOG.md)
[![endpoints](https://img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/endpoints.json)](openapi/openapi.yaml)
[![examples](https://img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/examples.json)](examples/)
[![release](https://img.shields.io/github/v/release/zimone91/monad-monitor-api?include_prereleases)](https://github.com/zimone91/monad-monitor-api/releases)
[![license](https://img.shields.io/github/license/zimone91/monad-monitor-api)](LICENSE)

## What it is

A read-only HTTP API for Monad mainnet validators.
It serves stake, commission, block production, rewards, delegators, liveness, a per-epoch slot ledger, a reliability score and network concentration.
The data comes from an indexer and a Monad node that the author runs.
No key or account is needed.

## Base URL

```text
https://api.zim.one/v1
```

| Operation | Path | Parameters besides `network` | Rate class |
|---|---|---|---|
| List validators | `GET /validators` | | heavy |
| Validator overview | `GET /validator/{id}` | | heavy |
| Reliability score | `GET /validator/{id}/score` | | heavy |
| Slot ledger | `GET /validator/{id}/slots` | `epochs`, 1 to 200, default about 7 days of epochs | heavy |
| Time series | `GET /validator/{id}/series` | `metric` (`production` by default, or `reward`), `bucket` (`1h`, `1d` by default, or `1w`), `from`, `to` | heavy |
| Top delegators | `GET /validator/{id}/delegators` | `limit`, 1 to 50, default 10 | heavy |
| Liveness events | `GET /validator/{id}/events` | `limit`, 1 to 200, default 50 | standard |
| Logo | `GET /validator/{id}/logo` | | logo |
| Network concentration | `GET /network/decentralization` | | heavy |
| Service health | `GET /health` | | standard |
| Data freshness | `GET /health/indexer` | | standard |

- `{id}` is a decimal validator id.
- `network` is `mainnet`, on every route except `/health` and `/health/indexer`. It is the default, so it can be left out. `network=testnet` returns `400 unsupported network`: testnet is not indexed, and an empty list is not an answer about a network.
- Responses are JSON, except the logo, which is an image (PNG, JPEG, GIF or WebP).
- CORS is open: `Access-Control-Allow-Origin: *`.
- The OpenAPI 3.1 document is served at `https://api.zim.one/v1/openapi.json`. It is the contract alone: paths, schemas, parameters, responses and headers, with no examples.
- [`openapi/openapi.yaml`](openapi/openapi.yaml) is the same contract with the captured example responses attached, and [`examples/`](examples/) holds those responses as separate files, each with its command and UTC capture time.

## First three requests

The commands use `curl` and `jq`, and validator 109, which the author operates.

### 1. The validator set

```sh
curl -s https://api.zim.one/v1/validators | jq '{count, first: .validators[0]}'
```

Look at `count` and at one entry: `validatorId`, `name`, `stake`.
`stake` is a whole number of wei in a string.

### 2. One validator

```sh
curl -s https://api.zim.one/v1/validator/109 | jq '{status, stake, commission, rankByStake, snapshot, lastProduction, time}'
```

`status` says whether it is in the consensus set: `Active`, `StakeTooLow`, or `NotInSet` for one that has left.
`snapshot.ts` dates the stake and `lastProduction.ts` dates the last block.
`time` dates only the response.
`commission` is a fraction scaled by 10^18: `"90000000000000000"` is 9 %.

### 3. Its reliability score

```sh
curl -s https://api.zim.one/v1/validator/109/score | jq '{value, confidence, coverage: .coverage.pct, configVersion, methodVersion, computedAt}'
```

Read `confidence` and `coverage` next to `value`.
`computedAt` says when the score was computed; it is recomputed at most every 10 minutes.

## Reading the data

- Check `GET /health/indexer` first. Its verdict is in the body, as `status`: `ok`, `degraded` or `down`. Read the body, not the status code.
- Amounts are integers in wei, sent as strings. 1 MON = 10^18 wei. Parse them with `BigInt` or a decimal type, never a float.
- `null` means not measured or not available. It never means zero.
- Check `status` before reading a validator's numbers. `NotInSet` means it is no longer in the consensus set: its `stake`, `commission` and `snapshot` are then the last values ever recorded for it, and everything that needs current membership — APR, rank by stake, voting weight, average blocks per epoch, stake changes, the reliability score — is `null`. A validator that left is not a validator scoring zero.
- `status` is `null` when this service cannot tell: the indexer's newest snapshot cycle is too old to say what the set is, or there is no stake reading for the validator yet. `GET /health/indexer` shows how old the newest cycle is.
- `GET /validators` lists every validator the indexer tracks, including those that have left the set. Its entries carry no `status`: `inConsensus: false` marks a validator that left.
- `time` is when the response was generated. Each reading carries its own clock: `snapshot.ts`, `computedAt`, `observedTo`, `fetchedAt`.
- `exact: false` or `status: "partial"` means the totals are a lower bound.
- The reliability score is this API's own method, not a value the network publishes. Compare scores only within one `configVersion`.

Details:

- [Reading the data](docs/reading-the-data.md)
- [Time fields](docs/time-fields.md)
- [Units](docs/units.md)
- [Coverage](docs/coverage.md)
- [Score method](docs/score-method.md)
- [Rate limits](docs/rate-limits.md)
- [Errors](docs/errors.md)
- [Versioning and deprecation](docs/versioning-and-deprecation.md)

## Verify it yourself

The commands below check the claims in this README against the live API.
They need `curl` and `jq`, and send at most three read-only requests per block.
A nightly CI job runs every block and fails when its output stops matching the pattern kept in an HTML comment above the block (visible in the Markdown source).

### The API answers and dates each response

`true` on the last line means `time` is within five minutes of your clock.

<!-- verify: ^ok\nmonad-monitor-api\n\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\ntrue$ -->
```sh
curl -s https://api.zim.one/v1/health | jq -r '.status, .service, .time, (now - (.time[0:19] + "Z" | fromdateiso8601) | . < 300 and . > -300)'
```

### Every JSON response carries `time`, errors included

A data route, an unknown validator and an unparseable time parameter.

<!-- verify: ^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\n){2}\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$ -->
```sh
curl -s 'https://api.zim.one/v1/validator/109/events?limit=1' | jq -r '.time'
curl -s https://api.zim.one/v1/validator/999999999 | jq -r '.time'
curl -s 'https://api.zim.one/v1/validator/109/series?from=yesterday' | jq -r '.time'
```

### Amounts are integer strings in wei

`stake` is wei in a string; `commission` is a fraction scaled by 10^18.

<!-- verify: ^\d+\nstring\n\d+$ -->
```sh
curl -s https://api.zim.one/v1/validator/109 | jq -r '.stake, (.stake | type), .commission'
```

### Readings carry their own clocks

The score's `computedAt` and the slot ledger's `observedTo` are timestamps of their own, separate from the response `time`.
Each is when that reading was taken; `time` is only when this response was written.

<!-- verify: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\n\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\n\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\n\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$ -->
```sh
curl -s https://api.zim.one/v1/validator/109/score | jq -r '.computedAt, .time'
curl -s https://api.zim.one/v1/validator/109/slots | jq -r '.observedTo, .time'
```

### Data may be cached for 60 seconds; health and errors may not

<!-- verify: (?i)^cache-control: public, max-age=60\r?\ncache-control: no-store\r?\ncache-control: no-store\r?$ -->
```sh
curl -s -D - -o /dev/null https://api.zim.one/v1/validator/109/score | grep -i '^cache-control'
curl -s -D - -o /dev/null https://api.zim.one/v1/health | grep -i '^cache-control'
curl -s -D - -o /dev/null https://api.zim.one/v1/validator/999999999 | grep -i '^cache-control'
```

### Each rate class reports its budget

`heavy` 120, `standard` 300 and `logo` 600 requests per minute, read from the response headers with one request per class.

<!-- verify: (?i)\A(?=[\s\S]*^ratelimit-remaining: \d+)(?=[\s\S]*^ratelimit-reset: \d+)[\s\S]*^ratelimit-limit: 120\r?\n[\s\S]*^ratelimit-limit: 300\r?\nratelimit-limit: 600\r?$ -->
```sh
curl -s -D - -o /dev/null https://api.zim.one/v1/validators | grep -i '^ratelimit-'
curl -s -D - -o /dev/null https://api.zim.one/v1/health | grep -i '^ratelimit-limit'
curl -sI https://api.zim.one/v1/validator/109/logo | grep -i '^ratelimit-limit'
```

### Bad requests get 4xx, not 5xx

An unknown validator is `404`; a malformed id and an id above 9223372036854775807 are `400`.

<!-- verify: ^\{[^\n]*"error":"validator not found"[^\n]*\} 404\n\{[^\n]*"error":"invalid validator id"[^\n]*\} 400\n\{[^\n]*"error":"invalid validator id"[^\n]*\} 400$ -->
```sh
curl -s -w ' %{http_code}\n' https://api.zim.one/v1/validator/999999999
curl -s -w ' %{http_code}\n' https://api.zim.one/v1/validator/12ab
curl -s -w ' %{http_code}\n' https://api.zim.one/v1/validator/99999999999999999999
```

### Security and CORS headers are set

<!-- verify: (?i)\A(?=[\s\S]*^strict-transport-security: max-age=\d+)(?=[\s\S]*^x-content-type-options: nosniff\r?$)(?=[\s\S]*^referrer-policy: no-referrer\r?$)(?=[\s\S]*^access-control-allow-origin: \*\r?$) -->
```sh
curl -s -D - -o /dev/null https://api.zim.one/v1/health | grep -iE '^(strict-transport-security|x-content-type-options|referrer-policy|access-control-allow-origin):'
```

### The API serves its own OpenAPI 3.1 document

The document names `https://api.zim.one/v1` as its server and carries no `time` field.

<!-- verify: ^3\.1\.\d+\n\d+\.\d+\.\d+\S*\nhttps://api\.zim\.one/v1\nfalse$ -->
```sh
curl -s https://api.zim.one/v1/openapi.json | jq -r '.openapi, .info.version, .servers[0].url, has("time")'
```

## Verify a release

This README describes release `v1.0.0-beta.1`.
Its date is in [CHANGELOG.md](CHANGELOG.md); while the changelog says `unreleased`, there is nothing to download yet.
Each release carries `openapi.yaml`, a `SHA256SUMS` file and a build provenance attestation for both.

```sh
gh release download v1.0.0-beta.1 --repo zimone91/monad-monitor-api --pattern openapi.yaml --pattern SHA256SUMS
sha256sum -c SHA256SUMS
gh attestation verify openapi.yaml --repo zimone91/monad-monitor-api
```

## Rate limits

Budgets are counted per client IP address, in fixed 60-second windows.

| Class | Requests per minute | Routes |
|---|---|---|
| `heavy` | 120 | `/validators`, `/validator/{id}`, `/validator/{id}/score`, `/validator/{id}/slots`, `/validator/{id}/series`, `/validator/{id}/delegators`, `/network/decentralization` |
| `standard` | 300 | `/validator/{id}/events`, `/health`, `/health/indexer`, `/openapi.json` |
| `logo` | 600 | `/validator/{id}/logo` |

Every response of these routes carries `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset` (seconds until the window ends).
`HEAD` counts like `GET`.
Over budget, the API answers `429`:

```text
HTTP/2 429
cache-control: no-store
ratelimit-limit: 120
ratelimit-remaining: 0
ratelimit-reset: 37
retry-after: 37

{"error":"rate limit exceeded","limitClass":"heavy","retryAfterSec":37,"time":"…"}
```

Honor `Retry-After`: wait that many seconds before the next request in that class.
If `429` repeats, double the wait each time and add random jitter.
Details: [docs/rate-limits.md](docs/rate-limits.md).

## Data and attribution

- Validator, stake, reward and block data are read from Monad mainnet (chain id 143) through a pool of public RPC endpoints (`rpc.monad.xyz`, `rpc1.monad.xyz`, `rpc2.monad.xyz`, `rpc3.monad.xyz`, `rpc-mainnet.monadinfra.com`), and stored by an indexer the author runs. An endpoint serves the indexer only after a check of its chain id, block freshness and latency.
- Reads the API makes on demand (delegator lists, the current epoch, balances) go to `rpc.monad.xyz`.
- Slot data — the per-epoch ledger behind `GET /validator/{id}/slots` and the reliability score — comes from consensus rounds observed by a Monad node the author runs. That node is the source of the slot data only; the chain reads above do not go through it.
- Validator names, descriptions, websites and logos come from the public [validator-info registry](https://github.com/monad-developers/validator-info), as published by the validators.
- Location fields (`geo` in `GET /validator/{id}`, and the country, city, provider and data-center axes of `GET /network/decentralization`) are derived offline from the network addresses that validator nodes publish to take part in consensus. The addresses themselves are not published.
- The location source is named in `geo.source`. Today it is GeoLite2: this product includes GeoLite2 data created by MaxMind, available from <https://www.maxmind.com>.
- A location can be contested. When two sources disagree about a validator, the fields they disagree on are listed in `geo.disputed`. Their values are still returned, as the first source's claim, and should not be shown as settled. They are left out of every concentration count, in `geo.concentration` and in `GET /network/decentralization`, rather than counted on a guess. `geo.disputed` is `null` when no second source was checked, and `[]` when both agreed.

Not verifiable from outside: the API keeps no access logs.
For a request that fails inside the server, it records the path, the time and the error, never the client address or the query string.
Client IP addresses serve only as rate-limit keys, are held in memory for at most ten minutes, and are never written to disk.

## License

The repository is licensed under the [MIT License](LICENSE).
Files in [`examples/`](examples/) contain third-party data: chain data from Monad mainnet, validator metadata from the validator-info registry, and fields derived from GeoLite2.
The repository license does not cover that data.
The documentation page is rendered with [Redoc](https://github.com/Redocly/redoc) (MIT); the site serves Redoc's bundle together with its license file.

## Contact

- Bugs and data questions: [GitHub issues](https://github.com/zimone91/monad-monitor-api/issues). Use the issue forms.
- Security reports: see [SECURITY.md](SECURITY.md). Do not open a public issue for anything exploitable.
