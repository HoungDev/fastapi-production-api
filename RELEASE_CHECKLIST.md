# Release Checklist

Use this checklist for every tagged release. A release is complete only after
the tag, GitHub Release, documentation, and post-release checks agree.

## Development version policy

`pyproject.toml` is the authoritative package version source. Runtime
`__version__`, FastAPI/OpenAPI metadata, the root endpoint, build artifacts,
release tags, and GitHub Release metadata must agree with it for a published
release.

Feature work for the next minor release may temporarily remain on the latest
published package version while the release is still in development. Artifacts
built from unreleased `main` during that period are development verification
artifacts only and must not be published, attached to a release, or otherwise
distributed as the already published release.

The version change for a new release belongs in an explicit release-preparation
change. Use a pre-release version such as `1.3.0rc1` when publishing a release
candidate. Set `1.3.0` only for the final v1.3.0 release commit.

## Prepare

- [ ] Confirm the target version follows Semantic Versioning.
- [ ] Confirm `SECURITY.md` identifies the release line that will receive
  security fixes after publication.
- [ ] Confirm the `Protect main` repository ruleset is active and requires the
  `Quality, tests, and package` check before merge.
- [ ] Confirm force-push and branch deletion remain blocked for `main`.
- [ ] Confirm no development build or artifact uses the same version identity
  as an already published release.
- [ ] Confirm the release version is aligned across package metadata,
  application metadata, changelog, tag, and release assets.
- [ ] Move completed entries from `Unreleased` into a dated changelog section.
- [ ] Review new dependencies and licenses.
- [ ] Confirm documentation describes current behavior and limitations.
- [ ] Confirm no credentials, databases, build output, or personal data are tracked.

## Validate

```bash
python scripts/dev.py check
```

- [ ] CI passes against PostgreSQL.
- [ ] The wheel smoke test imports `app.main` successfully.
- [ ] Installation was tested from a clean clone.
- [ ] Migrations were tested on an empty database.
- [ ] Authentication and health endpoints passed a smoke test.
- [ ] Dependency audit passes with `uv run pip-audit`.
- [ ] Distribution build passes with `uv build`.
- [ ] The release wheel is smoke-tested in an isolated environment.
- [ ] Alembic has exactly one head.
- [ ] The full migration chain upgrades successfully to `head`.
- [ ] The newest migration's rollback/forward procedure was verified against
  PostgreSQL when that release introduces schema changes.

## Publish

```bash
VERSION=vX.Y.Z
git tag -a "$VERSION" -m "$VERSION"
git push origin "$VERSION"
```

- [ ] Confirm the release commit is merged into the default branch.
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
- [ ] Close the completed release milestone.
- [ ] Open the next milestone and move unfinished work into it.
