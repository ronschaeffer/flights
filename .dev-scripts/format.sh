#!/bin/bash
# Format code using ruff

echo "🎨 Formatting code with ruff..."
ruff format .

echo "🔧 Fixing linting issues..."
ruff check . --fix

echo "✅ Code formatting complete!"