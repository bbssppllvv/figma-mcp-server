#!/bin/bash

# Figma MCP Server Setup Script

echo "🚀 Setting up Figma MCP Server..."

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.8+ required. Found: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check database
if [ ! -f "meta.db" ]; then
    echo "❌ Database file 'meta.db' not found!"
    echo "   Please ensure meta.db is in the current directory."
    exit 1
fi

echo "✅ Database found: meta.db"

# Check query aliases
if [ ! -f "config/query_aliases.yaml" ]; then
    echo "❌ Configuration file 'config/query_aliases.yaml' not found!"
    echo "   Please ensure config/query_aliases.yaml exists."
    exit 1
fi

echo "✅ Configuration found: config/query_aliases.yaml"

# Test import
echo "🧪 Testing MCP server import..."
python -c "import src.mcp_server; print('✅ MCP server imports successfully')" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "🎉 Setup completed successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "1. Set your OpenAI API key (recommended):"
    echo "   export OPENAI_API_KEY='your-api-key-here'"
    echo ""
    echo "2. Test the server:"
    echo "   python -m src.mcp_server"
    echo ""
    echo "3. Add to your MCP configuration:"
    echo "   See README.md for configuration examples"
else
    echo "❌ Setup failed. Please check the error messages above."
    exit 1
fi
