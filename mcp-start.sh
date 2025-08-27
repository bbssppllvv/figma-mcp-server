#!/bin/bash
# Figma MCP Server Launcher

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Environment variables
export FIGMA_DB="$SCRIPT_DIR/meta.db"
export PYTHONPATH="$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -f "venv/bin/python" ]; then
    echo "❌ Virtual environment not found. Please run setup.sh first." >&2
    exit 1
fi

# Check if database exists
if [ ! -f "meta.db" ]; then
    echo "❌ Database file 'meta.db' not found!" >&2
    exit 1
fi

# OpenAI API key is optional but recommended
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  WARNING: OPENAI_API_KEY not set. Semantic search will be disabled." >&2
    echo "   Set OPENAI_API_KEY for best search quality." >&2
else
    echo "✅ OPENAI_API_KEY found (length: ${#OPENAI_API_KEY})" >&2
fi

# Launch the MCP server
exec "$SCRIPT_DIR/venv/bin/python" "src/mcp_server.py"
