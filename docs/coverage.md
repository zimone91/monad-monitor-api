# Coverage

The API marks incomplete data instead of filling it in.
This page lists the fields that say how complete a reading is.

| Endpoint | Field | Meaning |
|---|---|---|
| any | `null` | Not measured or not available. Never zero. |
| slots | `buckets[].fullyObserved: false` | The epoch lies only partly inside observed round data. Its counts are a lower bound. |
| slots | `totals.exact: false` | At least one returned epoch is partial. The totals are a lower bound. |
| slots | `totals.status` | `exact`, `partial` or `empty`. Read this rather than `exact`: an empty ledger reports `exact: true`. |
| slots | `missedTruncated: true` | The list of missed rounds stops at 500 entries. The counts stay complete. |
| score | `coverage` | Share of the 7-day window in which the indexer recorded its snapshots. |
| score | `roundCoverage` | Share of the 7-day window covered by observed consensus rounds. |
| score | `uptimeSource` | `crisp`: slot counts back the `reliability` factor. `windowed`: time in the `live` state does. |
| score | `withheld: true` | No source can back the week. `value` is `null`. |
| score | `confidence` | `high`, `med` or `low`: how much evidence backs `value`. |
| score | `selfObservation` | `null` for most validators. When present, `expectedHiddenOwnSlots` is how many of this validator's own slots gaps in the round data could hide, and `crispWithheld: true` means its slot counts were not used. |
| overview | `income.aprSource` | `measured`: from rewards over a 24-hour window with at least 90 % coverage. `nominal`: an estimate from produced blocks, used otherwise. |
| overview | `geo` | `null` when no location is stored for the validator. |
| overview | `geo.disputed` | `null` means the location was not cross-checked against a second source. |
| overview | `geo.concentration` | `resolvedValidators` of `setValidators` could be located. Shares are of the whole set's stake, not of the located part. |
| decentralization | `axes.*.coverageStakeShare`, `axes.*.unknownStakeShare` | Share of stake whose value on that axis is known, or unknown. |
| decentralization | `axes.*.nakamoto33`, `axes.*.nakamoto67` | `null` when less than 90 % of stake is known on that axis. |
| decentralization | `axes.dataCenter.top[].partial: true` | The key lacks a city and falls back to `ASN-country`. |
| decentralization | `caveats` | Limits of the method, in words. Show them next to the numbers. |

## Slots: the open epoch is always partial

An epoch counts as fully observed only when one unbroken stretch of round data runs from the epoch before it into the epoch after it.
The current epoch has no successor yet.
A ledger that includes it therefore reads `status: "partial"` and `exact: false`; that is its normal state.
For totals over complete epochs only, add up the buckets with `fullyObserved: true`.

The ledger covers the last 7 days by default, the open epoch included.
The score's `reliability` factor counts full epochs only.
The two totals differ; label each with its window.

```sh
curl -s https://api.zim.one/v1/validator/109/slots | jq '{totals, observedTo, partialEpochs: [.buckets[] | select(.fullyObserved == false) | .epoch]}'
```

## Score: two coverage fields

`coverage` is about the indexer.
It snapshots the whole set every 5 minutes.
A gap of more than 10 minutes between snapshots is a blind spot and is listed in `coverage.gaps`.
`coverage.pct` is the observed share of the 7-day window.

`roundCoverage` is about consensus rounds observed by a Monad node the author runs.

| Field | Meaning |
|---|---|
| `pct` | Share of the window covered by round data |
| `coveredEpochs` | Epochs fully inside that coverage |
| `gateOpen` | `true` when the round data passed the set-wide checks: at least 90 % of the window, and of its epochs, observed, and recent enough |
| `reason` | `ok`, or why the gate is closed |

A validator's `reliability` factor uses slot counts (`uptimeSource: "crisp"`) only when the gate is open, the validator has about 200 assigned slots in the window or more, and it appears in at least 90 % of the covered epochs.
The slot threshold scales with the block rate.
`crispObservations` is the number of assigned slots behind the factor; it is `null` on the `windowed` path.

```sh
curl -s https://api.zim.one/v1/validator/109/score | jq '{withheld, uptimeSource, crispObservations, confidence, coverage, roundCoverage}'
```

## Confidence

| Path | `high` | `med` | `low` |
|---|---|---|---|
| Slot counts (`uptimeSource: "crisp"`) | Wilson interval at most 0.2 points wide | at most 1.9 points | wider |
| Time in `live` (`uptimeSource: "windowed"`) | at least 2000 blocks produced in 7 days (`observations7d`) | at least 200 | fewer |

The interval width is the measured slot share minus `crispLowerBoundPct`, the 95 % Wilson lower bound.
On the `windowed` path, `coverage.pct` below 80 lowers the label one step.
`confidence` is a label; it never changes `value`.

## Network concentration

```sh
curl -s https://api.zim.one/v1/network/decentralization | jq '{basis, caveats, dataCenter: (.axes.dataCenter | {coverageStakeShare, unknownStakeShare, nakamoto33, partialKeys: [.top[] | select(.partial) | .key]})}'
```

Unknown locations are excluded from the Nakamoto coefficients and reported as `unknownStakeShare`.
A share of what could be located is not a share of the network: show the denominator.
