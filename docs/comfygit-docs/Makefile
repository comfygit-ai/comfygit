.PHONY: help serve build generate-cli clean

help:
	@echo "serve / build: preview or strictly build the locked docs site"
	@echo "generate-cli: write parser help to ignored generated-cli/ for review"
	@echo "clean: remove generated artifacts only"

serve:
	uv run --frozen mkdocs serve

build:
	uv run --frozen mkdocs build --strict

generate-cli:
	cd ../.. && uv run --frozen --package comfygit python docs/comfygit-docs/scripts/generate_cli_reference.py

clean:
	rm -rf site/ generated-cli/
