# atlas-cli

The [Atlas](https://atlas.paranoid.software) method made executable: create an Atlas and keep
it in order while several people and agents work in it.

## Install

```bash
uv tool install paranoid-atlas-cli
```

## Develop

```bash
uv sync
uv run atlas --version
uv run pytest
```

## Release

Bump `version` in `pyproject.toml`, commit, then push a matching tag (`v0.1.1` for `0.1.1`):
the `Publish paranoid-atlas-cli to PyPI` workflow builds and publishes it. A tag that doesn't match the
version fails the workflow.
