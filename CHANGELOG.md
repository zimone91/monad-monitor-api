# Changelog

Notable changes to the API contract and this documentation are recorded here.
The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0-beta.2] - 2026-10-11

### Added

- `503 score unavailable` from `GET /validator/{id}/score` and `503 decentralization unavailable` from `GET /network/decentralization`, with `reason: "building"` and `Retry-After`: in the first seconds after the service starts, before its first score set is computed.

### Changed

- The score set is computed again every 10 minutes, behind the set being served, so a request no longer waits for a computation. `computedAt` is normally at most about 10 minutes plus one computation old. When a computation fails, the previous set stays served, and `computedAt` shows how old it is.
- `computedAt` of `GET /network/decentralization` is the time of the score set its delegation program verdicts come from: the same instant as the score's `computedAt`. Its stake and geolocation data are read at most 10 minutes before the response.
- `GET /validator/{id}/delegators` serves a list older than 10 minutes at once while a new reading runs behind it. Past 30 minutes the new reading runs first, and the request waits for it, up to 10 seconds, when it can finish in that time; otherwise the older list is served with its own `fetchedAt`.
- `GET /validator/{id}/delegators` answers `404` for a validator the chain does not list at the first reading only. A list once held is not removed when a later reading finds no such validator.

## [1.0.0-beta.1] - 2026-09-29

First public beta.

### Added

- Base URL `https://api.zim.one/v1`, the only supported path prefix.
- Eleven read operations: `GET /validators`, `GET /validator/{id}`, `GET /validator/{id}/score`, `GET /validator/{id}/slots`, `GET /validator/{id}/series`, `GET /validator/{id}/delegators`, `GET /validator/{id}/events`, `GET /validator/{id}/logo`, `GET /network/decentralization`, `GET /health` and `GET /health/indexer`.
- The OpenAPI 3.1 document for these operations at `GET /v1/openapi.json`, sent with `Cache-Control: public, max-age=300`, and as `openapi/openapi.yaml` in this repository.
- Rate limits per client IP address, in fixed 60-second windows: `heavy` 120, `standard` 300 and `logo` 600 requests. Every response of these routes carries `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset`. Over budget: `429` with `Retry-After`.
- Cache headers: `Cache-Control: public, max-age=60` on `200` responses of data routes, `no-store` on `/health`, `/health/indexer` and every error response, and `public, max-age=86400` on logos.
- Security headers: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
- `400` for a validator id above 9223372036854775807, and for a `from` or `to` in `/series` that cannot be parsed or is out of range.
- `400 unsupported network` for `network=testnet`, with `network` and `supported` in the body: `mainnet` is the only network this API serves.
- `503 delegators unavailable` from `GET /validator/{id}/delegators`, with `Retry-After`, when there is no list to give: the first reading takes longer than 10 seconds, too many readings are queued, or the chain reads failed. A `404` from that route means the validator is unknown.
- `status: "NotInSet"` for a validator that is no longer in the consensus set, alongside `Active` and `StakeTooLow`. Everything that needs current membership is then `null` rather than `0`: `income.aprPct`, `income.aprSource`, `rankByStake`, `votingWeightPct`, `epochAvgBlocks`, `stakeDelta` and `stakeExpectedRatio24h`.
- `withheldReason` in the score: `out-of-set` or `no-weekly-source` when `withheld` is `true`, `null` otherwise. A validator outside the consensus set receives no score and is not in `scoredSetSize`, so it neither gets a percentile nor moves anyone else's.
- `breakdown[].detail.openedBeforeWindow` in the score's `recovery` factor: `true` when a counted incident began before the 7-day window, in which case its duration is measured from its real start and `meanRecoveryMs` may exceed the window.
- Server errors answer with a generic body that carries an `errorId` and no internal error text.
- Captured responses in `examples/` and reference pages in `docs/`.

### Notes

- `rankByStake` and `votingWeightPct` are computed over the current consensus set, and `network/decentralization` over the same set. A validator that has left contributes to neither.
- Membership in the set is the indexer's verdict, `inConsensus`, and each member counts with its latest stake reading. A validator whose reading failed in one cycle stays in the set.
- `income.aprOperatorPct` is not part of `/v1`. The same value is published as `income.commissionReturnOnSelfStakePct`, which says what it is.
