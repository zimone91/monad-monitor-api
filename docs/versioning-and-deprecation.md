# Versioning and deprecation

## One supported prefix

`/v1` is the only supported path prefix for third parties.
Paths without a version prefix serve older clients.
They are outside this contract and may change or be removed without notice.

## Changes within v1

v1 grows by addition.
A change that can break a client is made only after a notice of at least 90 days; see [Deprecation](#deprecation).

| Change | Within v1 |
|---|---|
| New endpoint | Allowed |
| New field in a response | Allowed |
| New value in a field that names a state, source or status | Allowed |
| Rename or remove a field | Only after a 90-day notice |
| Change a field's type, unit or meaning | Only after a 90-day notice |
| Change the path, parameters or status codes of an existing case | Only after a 90-day notice |

A client that follows these rules keeps working as v1 grows:

- Ignore fields you do not know.
- Treat an unknown value of a known field as unknown, not as an error.
- Read fields by name; do not rely on their order.
- Expect `null` wherever a value can be unmeasured. Some fields appear only in certain states; the OpenAPI document lists which fields are required.

## Breaking changes

A breaking change is recorded in [CHANGELOG.md](../CHANGELOG.md).
It takes effect in v1 no earlier than 90 days after its announcement, or ships under a new major path, such as `/v2`, and leaves v1 as it is.

## Deprecation

Removing an endpoint or field, or changing one in a way that breaks a client, is announced at least 90 days before it happens.
When a new major version ships, the previous one stays available for at least 90 days after the announcement.

The announcement is a `Deprecated` entry in [CHANGELOG.md](../CHANGELOG.md) and a release note in this repository.
Those two are the whole notice channel: the API sends no `Deprecation` or `Sunset` response headers, so do not wait for one.

## Method changes are not breaking

The score's `configVersion` and `methodVersion` can change within v1.
A new method changes how `value` is computed, not the format of the response.
Scores under different `configVersion` are not comparable.
Method changes are recorded in [CHANGELOG.md](../CHANGELOG.md).

## Releases of this repository

Tags `v1.0.0-beta.N` version this documentation and the OpenAPI document.
`info.version` in the OpenAPI document is the tag without the leading `v`.
Beta means no SLA; the rules above apply during the beta as well.

```sh
curl -s https://api.zim.one/v1/openapi.json | jq -r '.openapi, .info.version'
curl -s https://api.zim.one/v1/validator/109/score | jq -r '.configVersion, .methodVersion'
```
