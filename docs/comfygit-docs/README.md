# ComfyGit documentation

The public site documents ComfyGit 0.7.0 at <https://docs.comfygit.org/>.
It is a separate uv project requiring Python 3.12 or newer. Its own `uv.lock`
controls the documentation dependencies; the monorepo lock controls the CLI.

## Preview and validate

From this directory:

```bash
uv sync --frozen
make serve
make build
```

Preview at `http://127.0.0.1:8000`. The strict build writes `site/` and fails on
warnings, including broken internal links. From the monorepo root, use
`make docs-serve` or `make docs-build`. `make clean` removes only generated output.

## Maintain the reference

The pages in `docs/cli-reference/` are curated, tracked source. Builds never
regenerate or overwrite them. After changing the parser, run:

```bash
make generate-cli
```

This uses the monorepo's local CLI to write all nested command help to ignored
`generated-cli/reference.md`. Compare that snapshot with the curated pages and
update their examples deliberately. See [scripts/README.md](scripts/README.md).

User guides live in `docs/user-guide/`, conceptual explanations in
`docs/concepts/`, and troubleshooting in `docs/troubleshooting/`. Add new pages
to `mkdocs.yml` and keep existing links working with redirects where appropriate.
For implementation guarantees, consult `../contracts/` and `../specs/` first.

## Dependency updates

Update the relevant dependency constraint and lockfile together, then build:

```bash
uv lock --upgrade-package mkdocs-material
make build
```

CI builds with the frozen lock and audits the docs dependencies. Theme updates
must reach the deployed HTML/assets to fix a vulnerability on the live site.

## Publish

After merging reviewed changes, run the **Publish Documentation** GitHub Actions
workflow on `main`. It builds with this lockfile, then commits the site to
`comfygit-ai/comfygit.github.io`, preserving its root `CNAME` and `README.md`.
The existing `DOCS_PUBLISH_TOKEN` Actions secret needs write access to that
Pages repository; do not embed credentials in Git URLs or checked-in files.

Do not use `mkdocs gh-deploy`: that targets the source repository's Pages branch,
which is not this site's deployment path. `make docs-deploy` at the repository
root prints the supported workflow instructions instead of publishing locally.

After the workflow succeeds, verify the actual page at
<https://docs.comfygit.org/getting-started/overview/> and its generator metadata.
The root URL is a redirect. Check navigation, search, and a changed page; a
successful push alone does not establish that Pages has served the new assets.
