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

# Check OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: OPENAI_API_KEY not set!" >&2
    echo "   Get your API key from: https://platform.openai.com/api-keys" >&2
    echo "   Then set: export OPENAI_API_KEY='your-key-here'" >&2
    exit 1
else
    echo "✅ OPENAI_API_KEY found (length: ${#OPENAI_API_KEY})" >&2
fi

# Launch the MCP server
exec "$SCRIPT_DIR/venv/bin/python" "src/mcp_server.py"
