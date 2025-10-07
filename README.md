# Firearm Safe Harbor Storage Location (FSH) Skid

[![Release Events](https://github.com/agrc/firearm-safe-harbor-skid/actions/workflows/release.yml/badge.svg)](https://github.com/agrc/firearm-safe-harbor-skid/actions/workflows/release.yml)
[![Push Events](https://github.com/agrc/firearm-safe-harbor-skid/actions/workflows/push.yml/badge.svg)](https://github.com/agrc/firearm-safe-harbor-skid/actions/workflows/push.yml)

This skid maintains an ArcGIS Online feature service for all of the law enforcement locations that are available to [receive firearms for safekeeping](https://bci.utah.gov/firearm-safe-harbor-storage-locations/) if the owner cohabitant or cohabitant believes that the owner cohabitant or another cohabitant with access to the firearm is an immediate threat to a cohabitant, the owner cohabitant, or another individual.

[Utah Code Title 53, Chapter 5a, Part 5](https://le.utah.gov/xcode/Title53/Chapter5A/53-5a-S502.html)

This skid is executed on demand by BCI employees with access managed by a Google Group. BCI manages the source data in a Google Sheet in a DPS-Firearm Map shared drive.

## Development

1. Create a virtual environment

   `uv venv`

1. Install development dependencies

   `uv sync --extra tests`

1. Rename secrets

   - `mv src/fsh/secrets/secrets.template.json src/fsh/secrets/secrets.json`

1. Populate secrets
1. Run skid

   `uv run fsh`

> [!Note]
> To update packages to their latest compatible versions:
>
> ```bash
> uv lock --upgrade  # Updates uv.lock with latest versions
> uv sync            # Installs the updated versions
> ```
