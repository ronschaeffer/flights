#!/bin/bash
# Run all tests

echo "🧪 Running tests..."

# Check if pytest is available
if command -v pytest >/dev/null 2>&1; then
    echo "Running with pytest..."
    pytest -v
else
    echo "pytest not found. Running basic Python tests..."
    # Run any test files directly with Python
    find . -name "test_*.py" -exec python {} \; 2>/dev/null || echo "No test files found"
fi

echo "✅ Tests complete!"