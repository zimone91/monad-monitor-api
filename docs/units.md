# Units

1 MON = 10^18 wei.
No field is in MON: every amount is in wei.

## Encodings

| Kind | Encoding | Fields |
|---|---|---|
| Amount | Integer number of wei in a JSON string. Negative only in `stakeDelta`. | `stake`, `selfStakeWei`, `authBalanceWei`, `income.unclaimedRewards`, `income.operatorUnclaimedWei`, `income.operatorCut.h24Wei`, `income.operatorCut.d7Wei`, `earned.h24Wei`, `earned.d7Wei`, `stakeDelta.epochWei`, `stakeDelta.d7Wei`, `validators[].stake`, `delegators[].stakeWei`, series `points[].value` and `points[].cumulative` with `metric=reward`, `basis.totalStakeWei`, `axes.*.top[].stakeWei`, `superminority.boundaryStakeWei` |
| Commission | Fraction scaled by 10^18, in a JSON string | `commission` |
| Percent, 0 to 100 | JSON number | `votingWeightPct`, `income.aprPct`, `epoch.progressPct`, `geo.concentration.country.stakePct`, `geo.concentration.asn.stakePct`, `geo.concentration.resolvedStakePct`, `coverage.pct`, `roundCoverage.pct`, `crispLowerBoundPct`, `percentileSet`, `percentileCohort`, `totals.crispPct` |
| Percent, unbounded | JSON number; can exceed 100 | `income.commissionReturnOnSelfStakePct` |
| Fraction, 0 to 1 | JSON number | In `GET /network/decentralization`: `stakeShare`, `hhiStake`, `unknownStakeShare`, `coverageStakeShare`, `basis.geoResolvedStakeShare`, `vdp.pass`, `vdp.fail`, `vdp.unknown`, `thresholdBreaches[].level`. In the score: `breakdown[].weight`, `breakdown[].effectiveWeight` |
| Ratio to stake | JSON number; 1.0 = exactly in proportion to stake | `epochPace`, `stakeExpectedRatio24h` |
| Score points, 0 to 100 | JSON number | `value`, `breakdown[].subScore`, `breakdown[].contribution` |
| Block count | JSON number | `production.produced24h`, `production.produced7d`, `blocksThisEpoch`, `epochAvgBlocks`, `observations7d` |
| Block count in a string | Integer in a JSON string | series `points[].value` with `metric=production` |
| Slot count | JSON number | `totals.assigned`, `totals.produced`, `totals.missed`, `buckets[].assigned`, `buckets[].produced`, `buckets[].missed`, `crispObservations` |
| Identifier or chain position | Integer in a JSON string | `validatorId`, `epoch.number`, `snapshot.blockNumber`, `lastProduction.blockNumber`, `lastProductionBlock`, `buckets[].epoch`, `buckets[].firstRound`, `buckets[].lastRound`, `missedRounds[].round`, `coverage[].fromRound`, `coverage[].toRound`, `events[].id`, `cycleSeq`, `finalizedBlock` |
| Duration | Milliseconds, JSON number | `liveness.windowMs`, `ageMs`, `okAgeMs`, `freshness.*AgeMs`, `coverage.observedMs`, `coverage.windowMs`, `roundCoverage.observedMs`, `roundCoverage.windowMs`, `blockRate.blockTimeMs` |
| Timestamp | ISO 8601 UTC string; Unix milliseconds in `epoch.endsAtMs`, `coverage.gaps[].startMs` and `coverage.gaps[].endMs` | See [time fields](time-fields.md) |

`income.commissionReturnOnSelfStakePct` is the operator's 7-day income, mostly commission on delegated stake, annualized and divided by the operator's own stake.
It is not a yield, and it is not comparable with `income.aprPct`: the numerator is earned on other people's stake and the denominator is only the operator's own, so it grows without bound as delegations grow.
The stakers' yield is `income.aprPct`, with its source in `income.aprSource`.
Both are `null` when `status` is `NotInSet`.

## Amounts: keep them exact

Parse wei with an integer or decimal type.
A JavaScript `Number` holds integers exactly only up to 2^53, which is 9007199254740992 wei, about 0.009 MON.
Beyond that, sums and comparisons go wrong without an error, even when the displayed value looks right.
The same applies to any tool that reads JSON numbers as doubles, including `jq` arithmetic.

JavaScript:

```js
const WEI_PER_MON = 10n ** 18n

const stake = BigInt('1500000000000000000') // 1.5 MON
const whole = stake / WEI_PER_MON // 1n
const rest = stake % WEI_PER_MON // 500000000000000000n wei
```

Python:

```python
from decimal import Decimal

stake = int("1500000000000000000")
print(Decimal(stake) / Decimal(10**18))  # 1.5
```

Keep conversion in one tested function and format for display only at the end.

## Commission

`commission` is a fraction scaled by 10^18.
`"90000000000000000"` is 0.09, which is 9 %.

```js
const bps = (BigInt('90000000000000000') * 10000n) / 10n ** 18n // 900n basis points = 9.00 %
```

## Percent or fraction

`*Pct` fields are on a 0 to 100 scale.
Shares in `GET /network/decentralization` are on a 0 to 1 scale.
Check the field before formatting it.

## See it

```sh
curl -s https://api.zim.one/v1/validator/109 | jq '{stake, commission, votingWeightPct, epochPace, production}'
```
