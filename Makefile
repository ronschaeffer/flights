# Makefile for consistent linting and formatting

.PHONY: lint format check fix install-hooks clean help pre-commit-all test ci-check deps

# Install pre-commit hooks
install-hooks:
	@echo "🔧 Installing pre-commit hooks..."
	pip install pre-commit
	pre-commit install

# Install project dependencies
deps:
	@echo "📦 Installing project dependencies..."
	pip install -r requirements.txt || echo "No requirements.txt found, install dependencies manually"

# Run all linting checks without fixing
check:
	@echo "🔍 Running all linting checks..."
	ruff check .
	ruff format --check .

# Run all linting checks and auto-fix issues
fix:
	@echo "🔧 Auto-fixing linting issues..."
	ruff check . --fix
	ruff format .

# Alias for fix
lint: fix

# Format code only
format:
	@echo "🎨 Formatting code..."
	ruff format .

# Clean tool caches
clean:
	@echo "🧹 Cleaning tool caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .coverage output logs storage 2>/dev/null || true

# Run pre-commit on all files
pre-commit-all:
	@echo "🚀 Running pre-commit on all files..."
	pre-commit run --all-files

# Run tests (if available)
test:
	@echo "🧪 Running tests..."
	@if command -v pytest >/dev/null 2>&1; then \
		pytest; \
	else \
		echo "pytest not installed, skipping tests"; \
	fi

# Full CI check (what runs in CI)
ci-check: check test
	@echo "✅ All CI checks passed!"

# Help
help:
	@echo "Available commands:"
	@echo "  make install-hooks  - Install pre-commit hooks"
	@echo "  make deps          - Install project dependencies"
	@echo "  make check         - Run linting checks without fixing"
	@echo "  make fix           - Auto-fix linting issues"
	@echo "  make lint          - Alias for fix"
	@echo "  make format        - Format code only"
	@echo "  make clean         - Remove tool caches and output files"
	@echo "  make pre-commit-all - Run pre-commit on all files"
	@echo "  make test          - Run tests (if pytest available)"
	@echo "  make ci-check      - Run full CI checks locally"
	@echo "  make help          - Show this help"