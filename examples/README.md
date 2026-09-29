# Examples

Live responses of the production API, one file per JSON operation. Each file is
the response body exactly as returned, except that long arrays keep only their
first entries; the last column names every cut. Nothing else is edited. The same
bodies are the `live` examples in `openapi/openapi.yaml`.

Every capture is taken on `/v1`, the documented prefix, from the deployed
release this documentation describes.

`time` in each body is the moment the server generated it. The capture time
below is the client clock (UTC) read immediately before the request.

| File | Operation | Captured (UTC) | Command | Truncation |
|---|---|---|---|---|
| `listValidators.json` | `GET /validators` | 2026-09-29T00:03:46Z | `curl -sS 'https://api.zim.one/v1/validators?network=mainnet'` | `validators` truncated to 3 of 202 |
| `getValidator.json` | `GET /validator/{id}` | 2026-09-29T00:03:48Z | `curl -sS 'https://api.zim.one/v1/validator/109?network=mainnet'` | not truncated |
| `getValidatorScore.json` | `GET /validator/{id}/score` | 2026-09-29T00:03:49Z | `curl -sS 'https://api.zim.one/v1/validator/109/score?network=mainnet'` | `breakdown` truncated to 5 of 6 |
| `getValidatorSlots.json` | `GET /validator/{id}/slots` | 2026-09-29T00:03:51Z | `curl -sS 'https://api.zim.one/v1/validator/109/slots?network=mainnet'` | `buckets` truncated to 5 of 40 |
| `getValidatorSeries.json` | `GET /validator/{id}/series` | 2026-09-29T00:03:52Z | `curl -sS 'https://api.zim.one/v1/validator/109/series?network=mainnet&metric=production&bucket=1d'` | `points` truncated to 5 of 8 |
| `getValidatorDelegators.json` | `GET /validator/{id}/delegators` | 2026-09-29T00:03:54Z | `curl -sS 'https://api.zim.one/v1/validator/109/delegators?network=mainnet&limit=2'` | not truncated |
| `getValidatorEvents.json` | `GET /validator/{id}/events` | 2026-09-29T00:03:55Z | `curl -sS 'https://api.zim.one/v1/validator/109/events?network=mainnet&limit=5'` | not truncated |
| `getNetworkDecentralization.json` | `GET /network/decentralization` | 2026-09-29T00:03:57Z | `curl -sS 'https://api.zim.one/v1/network/decentralization?network=mainnet'` | `axes.validator.top` truncated to 5 of 10, `axes.country.top` truncated to 5 of 10, `axes.provider.top` truncated to 5 of 10, `axes.city.top` truncated to 5 of 10, `axes.dataCenter.top` truncated to 5 of 10, `superminority.memberIds` truncated to 5 of 19 |
| `getHealth.json` | `GET /health` | 2026-09-29T00:03:59Z | `curl -sS 'https://api.zim.one/v1/health'` | not truncated |
| `getIndexerHealth.json` | `GET /health/indexer` | 2026-09-29T00:04:00Z | `curl -sS 'https://api.zim.one/v1/health/indexer'` | not truncated |

`GET /validator/{id}/logo` has no example file: it returns a binary image.
