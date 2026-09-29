# Contributing

This repository has a single maintainer.

## Issues

Issues are welcome.
Open one with a form:

| Form | Use it for |
|---|---|
| API bug | An endpoint that answers wrongly or not at all |
| Data question | A value that looks wrong or unclear |
| Docs error | A mistake or gap in this documentation |

Include the exact request, the UTC `time` from the response, and what you expected.
Before filing a data question, check [Reading the data](docs/reading-the-data.md).

## Pull requests

Pull requests are not accepted: this is a single-author repository, and every change is made and signed by the maintainer.
An issue that describes the change is the way to propose it.

## Running the checks

The scripts in `.github/scripts/` that scan the whole repository list its files from the git index (`git ls-files`), so run them after `git add`: a file that is not added is not checked, and when no file is, they stop with `CANNOT CHECK` rather than pass.

## Security

Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
