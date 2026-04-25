#!/bin/bash

echo "Setting up FitScript..."

# Check Python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found. Please install it from python.org"
    exit 1
fi

# Install Flask if not already installed
pip3 install flask --quiet

# Run the app
echo "Starting FitScript at http://localhost:5000"
python3 app.py