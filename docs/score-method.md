# Score method

The reliability score in `GET /validator/{id}/score` is this API's own method.
It is not a value the Monad network publishes, and it is not an independent rating.
The author operates validator 109, which the examples use.

The full method write-up is not published yet.
This page summarizes what the response itself states.

## Overview

| Item | In the response |
|---|---|
| Scale | `value`, 0 to 100 |
| Window | The last 7 days: `coverage.windowMs` is 604800000 |
| Set | The validators that receive a score: `scoredSetSize`. A withheld validator is not in it, so one that has left the consensus set neither gets a percentile nor moves anyone else's |
| Recomputed | At most every 10 minutes: `computedAt` |
| Method | `configVersion` (`v3` at the time of writing) and `methodVersion` (`crisp-point-1`) |

## Factors

| `factor` | `weight` | What it scores |
|---|---|---|
| `reliability` | 0.5 | Produced ÷ assigned slots over the full epochs of the window (`uptimeSource: "crisp"`). A ceiling derived from the share of observed time in the `live` state also applies. While the validator is `suspect`, `stale` or `critical`, the factor is capped at 40, 20 or 0. Without enough slot data: the share of observed time in `live` (`uptimeSource: "windowed"`). |
| `epochParticipation` | 0.2222 | Share of the window's full epochs in which the validator produced at least one block. Needs at least 5 observed full epochs. |
| `recovery` | 0.1667 | 100 with no incidents in the window; 0 with no recovery from a current bad state. Otherwise it falls with the mean time back to `live`: about 98 for 5 minutes, 78 for 1 hour, 37 for 6 hours, 13 for 24 hours. Each incident after the first removes a further 15 % of that. An incident that began before the window is measured from its real start, so `detail.meanRecoveryMs` can exceed the window and `detail.openedBeforeWindow` is `true`. |
| `rewardConsistency` | 0.1111 | Variation of per-epoch rewards over the last 5 complete epochs, beyond the variation expected by chance from stake-weighted block assignment. |
| `vdp` | 0 | Not part of the score. Reported beside it as `vdpStatus`. |
| `commissionStability` | 0 | Not fed with data; always `dropped`. |

Each factor gives a `subScore` from 0 to 100, or `null`.
A factor with `null` is `dropped`, and the weights of the others are scaled to add up to 1 (`effectiveWeight`).
`contribution` is `subScore` × `effectiveWeight`, and the contributions add up to `value` within rounding.
`reason` says in words what each factor counted.

```sh
curl -s https://api.zim.one/v1/validator/109/score | jq '{value, confidence, configVersion, methodVersion, computedAt, factors: [.breakdown[] | {factor, weight, effectiveWeight, subScore, status, reason}]}'
```

## Confidence and coverage

`confidence` (`high`, `med`, `low`) says how much evidence backs `value` and never changes it.
`crispLowerBoundPct` is the 95 % Wilson lower bound of the slot share.
`coverage` and `roundCoverage` say how much of the window was observed.
Details: [coverage](coverage.md).

## Withheld

`withheld: true` means the week cannot be judged.
`value`, `percentileSet` and `percentileCohort` are then `null`: show a dash, not 0.
`withheldReason` says which case it is.

| `withheldReason` | Meaning |
|---|---|
| `out-of-set` | The validator is not in the consensus set (`status` is `NotInSet`), so there is no week of participation to score |
| `no-weekly-source` | No source covers the window yet: a validator younger than it, or a gap in observation |

## Percentiles

| Field | Compared with |
|---|---|
| `percentileSet` | The whole scored set (`scoredSetSize`) |
| `percentileCohort` | Validators within 30 % of this validator's stake (`cohortSize`, this validator included; 1 means no peers) |

Ties count half.
Under `v3`, the order uses the evidence behind the `reliability` factor (its Wilson lower bound), not `value`.
Many validators share `value: 100`; among them, more assigned slots rank higher, and assigned slots follow stake.
A percentile difference on that plateau is not a quality difference.

## Versions

| Field | Meaning |
|---|---|
| `configVersion` | Version of the method |
| `methodVersion` | Measurement behind the `reliability` factor |
| `sourceChangedAt` | When that measurement last changed |

Values under different `configVersion` are not comparable.
A new `configVersion` is a change of method, not a change in the validators.
Method changes are recorded in [CHANGELOG.md](../CHANGELOG.md).

## Beside the score

- `vdpStatus` (`pass`, `fail`, `unknown`) is this API's reading of whether the validator meets the commission and uptime bar of the Monad Foundation's validator delegation program. `vdpStatusReason` says why. `unknown` is not a failure.
- `longevity.firstBlockDay` is display-only and a lower bound.
- `currentState` is the liveness verdict at `computedAt`.
