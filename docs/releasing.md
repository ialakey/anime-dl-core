# Releasing

Everything is done by CI from a tag. Two workflows react to a `v*` tag:

* [`build.yml`](../.github/workflows/build.yml) — tests, builds sdist + wheel,
  installs the wheel into a clean environment and creates the GitHub release
  with the artifacts, their SHA-256 and the commit they came from.
* [`publish-pypi.yml`](../.github/workflows/publish-pypi.yml) — builds again
  from the tagged commit and uploads to PyPI.

## Cutting a release

1. Bump the version in **both** places (they must agree — CI checks it against
   the tag):
   * `pyproject.toml` → `version`
   * `src/anime_dl_core/__init__.py` → `__version__`
2. Add the entry to `CHANGELOG.md` and `CHANGELOG.ru.md`.
3. Commit, tag, push:

   ```bash
   git commit -am "release 0.4.0"
   git push origin main
   git tag -a v0.4.0 -m "anime-dl-core v0.4.0"
   git push origin v0.4.0
   ```

4. Watch the runs: `gh run watch` — or the Actions tab.

A push to `main` without a tag is enough for a build: it refreshes the rolling
`latest` pre-release, so the current build is always one URL away. PyPI is only
touched by a tag.

## Enabling PyPI publishing (once)

Until this is done, the publish job stays green and prints a notice instead of
uploading — a release tag should not fail because publishing is not set up yet.

### Option 1 — Trusted Publishing (recommended)

No token is created, stored or rotated: PyPI accepts a short-lived OIDC token
that GitHub issues to this repository only.

1. Sign in to [pypi.org](https://pypi.org/) → **Your account** → **Publishing**
   → **Add a new pending publisher**:
   * PyPI Project Name: `anime-dl-core`
   * Owner: `ialakey`
   * Repository name: `anime-dl-core`
   * Workflow name: `publish-pypi.yml`
   * Environment name: *leave empty*
2. In the repository: **Settings → Secrets and variables → Actions →
   Variables** → **New repository variable**
   * Name: `PYPI_TRUSTED_PUBLISHING`
   * Value: `true`
3. Push a `v*` tag. The first successful upload turns the pending publisher into
   a normal one.

If the project already exists on PyPI (for example it was first uploaded with a
token), a *pending* publisher is not the right form — add it on the project
itself instead: **Your projects → anime-dl-core → Manage → Publishing → Add a
new publisher**, with the same owner, repository and workflow name.

To check the credentials without cutting a release, run the workflow manually:
**Actions → Publish to PyPI → Run workflow**, target `pypi`. A manual run passes
`skip-existing`, so an already published version is skipped instead of failing —
the point of the run is the authentication, not the upload.

### Option 2 — API token

1. On PyPI: **Your account → API tokens → Add API token**. Before the project
   exists the token has to be account-scoped; after the first upload, replace it
   with a token scoped to `anime-dl-core` alone.
2. In the repository: **Settings → Secrets and variables → Actions → Secrets**
   → **New repository secret**
   * Name: `PYPI_API_TOKEN`
   * Value: the token, `pypi-` prefix included
3. Push a `v*` tag. The token takes precedence over Trusted Publishing when
   both are configured — so to switch back to OIDC, delete the secret and set
   the variable.

## TestPyPI

Useful for rehearsing the upload without burning a version number on PyPI (a
version can never be re-uploaded there).

1. Register on [test.pypi.org](https://test.pypi.org/), create a token and add
   it as the `TEST_PYPI_API_TOKEN` secret.
2. Actions → **Publish to PyPI** → **Run workflow** → target: `testpypi`.
3. Check the result:

   ```bash
   pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ anime-dl-core
   ```

## After the release

```bash
pip install --upgrade anime-dl-core
python -c "import anime_dl_core; print(anime_dl_core.__version__)"
anime-dl-core --list
```

The GitHub release carries the same wheel and sdist plus `dist-sha256.txt`, so a
download can always be checked against the run that produced it.
