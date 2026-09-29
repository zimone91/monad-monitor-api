# Reading the data

Rules for reading responses from `https://api.zim.one/v1`.
Each rule follows from how the data is collected.

| Rule | In practice | Details |
|---|---|---|
| Check freshness first | Read `status` of `GET /health/indexer` before trusting any reading. | [below](#check-freshness-first) |
| Amounts are wei in strings | Parse them with `BigInt` or a decimal type, never a float. 1 MON = 10^18 wei. | [units](units.md) |
| `null` means not measured | Show "not measured". Never show it as 0. | [below](#null-is-not-zero) |
| Each reading has its own clock | `time` dates the response. `snapshot.ts`, `computedAt`, `observedTo` and `fetchedAt` date the readings. | [time fields](time-fields.md) |
| Coverage is explicit | `exact: false`, `status: "partial"`, `fullyObserved: false` and `partial: true` mark incomplete data. Totals are then a lower bound. | [coverage](coverage.md) |
| The score is a method | The reliability score is this API's own method. It is not a value the network publishes and not an independent rating. | [score method](score-method.md) |
| Ranks name their basis | `rankByStake` and `rankByBlocks24h` order different things. Label each rank with its basis. | [below](#ranks) |
| Ratios near 1 are neutral | `epochPace` and `stakeExpectedRatio24h` compare production with stake. Near 1 means in line with stake. | [below](#ratios) |

All of these are visible in one response:

```sh
curl -s https://api.zim.one/v1/validator/109 | jq '{time, snapshot, lastProduction, stake, commission, rankByStake, rankByBlocks24h, epochPace, stakeExpectedRatio24h}'
```

## Check freshness first

`GET /health/indexer` answers with HTTP 200 and a verdict in `status`.

| `status` | Meaning |
|---|---|
| `ok` | The last indexer cycle is recent and its tables are current. |
| `degraded` | Cycles run, but a cycle failed to commit or a table fell behind. `reason` says which. |
| `down` | No indexer cycle started for 15 minutes, or no heartbeat exists. |

```sh
curl -s https://api.zim.one/v1/health/indexer | jq '{status, reason, ageMs, freshness}'
```

`GET /health` only says that the API process runs.
It answers `ok` even when the data is stale.

## `null` is not zero

A field is `null` when the value was not measured or is not available.
`0` is a measured zero.
Examples:

- `epochPace` is `null` in the first 5 % of an epoch, where the ratio is too noisy to publish.
- `stakeDelta.d7Wei` is `null` until a snapshot from 7 days ago exists.
- `value` in the score is `null` when `withheld` is `true`; `withheldReason` says why.
- Everything that needs current set membership is `null` when `status` is `NotInSet`: `income.aprPct`, `income.aprSource`, `rankByStake`, `votingWeightPct`, `epochAvgBlocks`, `stakeDelta`, `stakeExpectedRatio24h`, and the score.

Show `null` as "not measured" or a dash, with the time you read it.

## Ranks

| Field | Ordered by | Over |
|---|---|---|
| `rankByStake` | Consensus stake at the latest snapshot, 1 = highest | The current consensus set (`setSize`); `null` outside it |
| `rankByBlocks24h` | Blocks produced in the last 24 hours, 1 = most | The current consensus set (`setSize`); `null` outside it |
| `epochRank` | Blocks produced since the current epoch started, 1 = most | The current consensus set; `null` outside it |
| `percentileSet`, `percentileCohort` | Evidence behind the reliability score | The scored set, or validators within 30 % of this validator's stake |

Write the basis next to the number: "by stake", "by blocks, last 24 h", "by blocks, this epoch".
Without its basis, a rank reads as a quality ranking; the stake and block ranks are not one.

## Ratios

| Field | Formula | Window |
|---|---|---|
| `epochPace` | Blocks produced ÷ (stake share × blocks the set produced) | Since the current epoch started |
| `stakeExpectedRatio24h` | Blocks produced ÷ (stake share × network blocks) | Last 24 hours |

1.0 means production exactly in proportion to stake.
Block assignment is random per round, so values near 1 are ordinary variation: describe them as "in line with stake", not as "ahead" or "behind".
The API publishes no threshold for "near".
The two ratios cover different windows and can point in different directions in the same response.

## Paths inside a body

`meta.logoUrl` in `GET /validator/{id}` and `logoUrl` in `GET /validators` are paths, for example `/validator/109/logo?network=mainnet`.
Append them to the base URL `https://api.zim.one/v1` as strings.
Resolving them as URL references drops the `/v1` prefix.
