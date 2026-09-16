# Documentation scripts

`generate_cli_reference.py` takes the current CLI parser's help for every command
and nested subcommand. It writes a review snapshot to ignored
`generated-cli/reference.md`; it never touches the curated pages under `docs/`.

From `docs/comfygit-docs`, run `make generate-cli`. Alternatively, from the
monorepo root:

```bash
uv run --frozen --package comfygit python docs/comfygit-docs/scripts/generate_cli_reference.py
```

Use the snapshot to review command examples after a parser change. Update the
curated reference and relevant guides, then run `make docs-build` from the root.
Build and serve do not generate reference files automatically.
