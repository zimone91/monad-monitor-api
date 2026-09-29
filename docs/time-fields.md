# Time fields

Every JSON response carries `time`: the moment the server generated that response.
It is not an observation time.
A recent `time` does not make the readings in the body recent.
Each reading carries its own timestamp, listed below by endpoint.

All times are UTC.
Timestamps are ISO 8601 strings, except `epoch.endsAtMs`, `coverage.gaps[].startMs` and `coverage.gaps[].endMs`, which are Unix milliseconds.
The ages in `GET /health/indexer` are durations in milliseconds.
Most strings carry milliseconds; `sourceChangedAt` and `builtAt` may not, so parse them with a full ISO 8601 parser.

## Every endpoint

| Field | Clock |
|---|---|
| `time` | When this response was generated, by the server clock. Present on every JSON body, errors included. `/v1/openapi.json` carries none. |

## `GET /validator/{id}`

| Field | Clock |
|---|---|
| `snapshot.ts` | Start of the indexer cycle that read this validator's stake and commission. `snapshot.blockNumber` is the finalized block read in that cycle. |
| `liveness.updatedAt` | When the indexer last wrote this validator's liveness verdict. |
| `lastProduction.ts` | Estimated time of the last block this validator produced. The indexer derives it from the block's distance to the finalized head at the measured block rate. It is not the block header's timestamp. |
| `epoch.endsAtMs` | Projected end of the current epoch: the remaining blocks at the measured block rate, counted from when the overview was assembled. A projection, not an observation. Unix milliseconds; may carry a fraction. |
| `geo.updatedAt` | When the location attribution was last written. |

The overview is kept for 60 seconds per validator.
After that, the kept copy is still served while a new one is assembled, for at most 5 minutes after it was assembled.
An older copy is never served: the request waits for a new one.
The body has no assembly time: date its readings by `snapshot.ts`, `liveness.updatedAt` and `lastProduction.ts`.

## `GET /validator/{id}/score`

| Field | Clock |
|---|---|
| `computedAt` | When the whole set was scored. The result is kept for 10 minutes; the next request after that waits for a new computation. `computedAt` is therefore at most about 10 minutes older than `time`. |
| `currentState` | The liveness verdict at `computedAt`, not at `time`. For the verdict now, read `liveness.state` in `GET /validator/{id}`. |
| `sourceChangedAt` | When the measurement behind the `reliability` factor last changed on this network. Present when `configVersion` is `v3`. |
| `coverage.gaps[].startMs`, `coverage.gaps[].endMs` | Start and end of each indexer blind spot inside the 7-day window. Unix milliseconds. |
| `longevity.firstBlockDay` | First UTC day with a produced block in the indexer's records, as `YYYY-MM-DD`. A lower bound: the records may start after the validator did. |

## `GET /validator/{id}/slots`

| Field | Clock |
|---|---|
| `observedTo` | Newest write of round data for this validator. `null` when nothing was observed. |
| `buckets[].missedRounds[].ts` | Time of each missed round, as observed. |
| `coverage[].fromTs`, `coverage[].toTs` | First and last observed round of each unbroken stretch of round data. |

## `GET /validator/{id}/series`

| Field | Clock |
|---|---|
| `from`, `to` | The window the response covers. Defaults: 24 hours for `bucket=1h`, 7 days for `1d`, 12 weeks for `1w`, ending now. `1d` and `1w` reach back at most 90 days. |
| `points[].ts` | Start of the bucket: the UTC hour, the UTC day, or Monday 00:00 UTC. Blocks are placed by their estimated time, as in `lastProduction.ts`. |

`from` and `to` accept Unix milliseconds or an ISO 8601 date, from 1970-01-01T00:00:00.000Z through 9999-12-31T23:59:59.999Z.
A value that cannot be parsed or is out of range returns `400` with `"error":"invalid time"`.
Buckets of `1d` and `1w` count whole UTC days, so the first bucket can include blocks from before `from`.
When the window reaches the present, the last bucket is still filling.

## `GET /validator/{id}/delegators`

| Field | Clock |
|---|---|
| `fetchedAt` | When this list was read from the chain. A list is kept for 10 minutes; an older list is served while a new read runs, so `fetchedAt` can be older than 10 minutes. |

## `GET /validator/{id}/events`

| Field | Clock |
|---|---|
| `events[].ts` | Time of the indexer cycle that recorded the state change. |

## `GET /network/decentralization`

| Field | Clock |
|---|---|
| `computedAt` | When the whole set was computed. Kept for 10 minutes, like the score. |

## `GET /health` and `GET /health/indexer`

| Field | Clock |
|---|---|
| `builtAt` | When the running build of the API was made. |
| `ageMs` | Milliseconds since the last indexer cycle started. |
| `okAgeMs` | Milliseconds since the last indexer cycle that committed its data. `null` if none did. |
| `freshness.snapshotsAgeMs` | Milliseconds since the newest stake snapshot. |
| `freshness.livenessAgeMs` | Milliseconds since the newest liveness verdict. |
| `freshness.blockRewardsAgeMs` | Milliseconds since the newest recorded block, by its estimated time. |

The ages are taken with the same clock as `time`.
Subtract an age from `time` to get the moment it refers to.

## See it

```sh
curl -s https://api.zim.one/v1/validator/109/score | jq '{time, computedAt, sourceChangedAt}'
curl -s https://api.zim.one/v1/health/indexer | jq '{time, ageMs, okAgeMs, freshness}'
```
