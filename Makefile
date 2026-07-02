.PHONY: install test lint format typecheck run-api clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src/scireview

run-api:
	uvicorn scireview.api.app:create_app --factory --reload

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
