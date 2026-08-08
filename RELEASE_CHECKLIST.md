# Release Checklist

Use this checklist for every tagged release. A release is complete only after
the tag, GitHub Release, documentation, and post-release checks agree.

## Prepare

- [ ] Confirm the target version follows Semantic Versioning.
- [ ] Confirm `pyproject.toml`, application OpenAPI, and root endpoint agree.
- [ ] Move completed entries from `Unreleased` into a dated changelog section.
- [ ] Review new dependencies and licenses.
- [ ] Confirm documentation describes current behavior and limitations.
- [ ] Confirm no credentials, databases, build output, or personal data are tracked.

## Validate

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run alembic upgrade head
uv run pytest
uv run pip-audit
uv build
```

- [ ] CI passes against PostgreSQL.
- [ ] The wheel smoke test imports `app.main` successfully.
- [ ] Installation was tested from a clean clone.
- [ ] Migrations were tested on an empty database.
- [ ] Authentication and health endpoints passed a smoke test.

## Publish

```bash
git tag -a v1.0.1 -m "v1.0.1"
git push origin v1.0.1
```

- [ ] Create a GitHub Release from the annotated tag.
- [ ] Copy the matching changelog section into the release notes.
- [ ] Include highlights, upgrade instructions, known limitations, and checksums
  when distributing artifacts.
- [ ] Mark pre-release status correctly.

## Verify and announce

- [ ] Re-run the documented Quick Start from the release tag.
- [ ] Verify the CI and release badges.
- [ ] Verify the Sponsor button and community links.
- [ ] Announce the release in GitHub Discussions.
- [ ] Open the next milestone and move unfinished work into it.
