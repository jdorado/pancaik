#!/bin/bash

# Remove unused imports (excluding __init__.py files)
poetry run autoflake --in-place --remove-all-unused-imports --recursive --exclude "__init__.py" . || { echo "autoflake failed"; exit 1; }

# Run black on the entire project
poetry run black . || { echo "black failed"; exit 1; }

# Run isort on the entire project
poetry run isort . || { echo "isort failed"; exit 1; }

echo "Formatting completed successfully!" 