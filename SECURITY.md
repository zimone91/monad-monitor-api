# Security policy

Report vulnerabilities privately.
Do not open a public issue for anything exploitable.

## How to report

- On GitHub: [Report a vulnerability](https://github.com/zimone91/monad-monitor-api/security/advisories/new) on this repository.
- By email: <privacy@zim.one>.

Please include:

- the endpoint and the exact request;
- the response: status, headers and body, including `time` and any `errorId`;
- what an attacker gains, and the conditions it needs.

## What to expect

- A first response within 7 days.
- Fixed issues are listed under `Security` in [CHANGELOG.md](CHANGELOG.md), with credit if you want it.
- There is no bug bounty.

## Scope

In scope:

- the API at `api.zim.one`;
- this documentation and the OpenAPI document.

Out of scope:

- third-party services, including GitHub and the services behind the badges;
- the Monad network itself;
- social engineering;
- volumetric denial of service.

Test within the published [rate limits](docs/rate-limits.md), and do not load-test the API.

## Supported versions

Only the API as currently deployed and the latest version of this documentation receive fixes.
