.PHONY: test

test:
	uv run --no-sync --with pytest pytest -q
