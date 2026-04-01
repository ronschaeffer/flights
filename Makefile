.PHONY: lint format check fix install-hooks clean pre-commit-all test ci-check help

install-hooks:
	@echo "Installing pre-commit hooks..."
	poetry run pre-commit install

check:
	@echo "Running all linting checks..."
	poetry run ruff check .
	poetry run ruff format --check .

fix:
	@echo "Auto-fixing linting issues..."
	poetry run ruff check . --fix
	poetry run ruff format .

lint: fix

format:
	@echo "Formatting code..."
	poetry run ruff format .

clean:
	@echo "Cleaning tool caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .coverage 2>/dev/null || true

pre-commit-all:
	@echo "Running pre-commit on all files..."
	poetry run pre-commit run --all-files

test:
	@echo "Running tests..."
	poetry run pytest

ci-check: check test
	@echo "All CI checks passed!"

help:
	@echo "Available commands:"
	@echo "  make install-hooks   - Install pre-commit hooks"
	@echo "  make check           - Run linting checks without fixing"
	@echo "  make fix             - Auto-fix linting issues"
	@echo "  make lint            - Alias for fix"
	@echo "  make format          - Format code only"
	@echo "  make clean           - Remove tool caches"
	@echo "  make pre-commit-all  - Run pre-commit on all files"
	@echo "  make test            - Run tests"
	@echo "  make ci-check        - Run full CI checks locally"
	@echo "  make help            - Show this help"
