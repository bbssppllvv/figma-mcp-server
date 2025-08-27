# Figma Documentation MCP Server

MCP (Model Context Protocol) server that provides instant access to Figma Plugin API documentation and community code examples for LLM agents and developers.

## What This Is

This server contains the complete Figma Plugin API documentation plus hundreds of real-world code examples from open source plugins, all searchable locally. It enables LLM agents to quickly find accurate API information and working code patterns without making mistakes or using outdated information.

## Why This Exists

Writing Figma plugins requires constant reference to documentation and working examples. This server provides:

- Complete official Figma API documentation (Plugin API, Widget API, REST API)
- 316 community plugin repositories with real code examples
- All content indexed and searchable with semantic understanding
- Instant local access without internet dependencies
- MIT licensed code examples ready for use

## Installation

```bash
git clone https://github.com/bbssppllvv/figma-mcp-server.git
cd figma-mcp-server
./setup.sh
```

Set OpenAI API key:
```bash
export OPENAI_API_KEY="your-key-here"
```

Test the installation:
```bash
python -m src.mcp_server
# Should show: MCP server running on stdio
```

## Usage with Cursor

1. Copy `cursor-mcp-config.json` to your `.cursor/mcp.json`
2. Replace `/absolute/path/to/figma-mcp-server` with your actual path
3. Add your OpenAI API key

**Important:** Use absolute paths and avoid spaces in directory names.

Example configuration:
```json
{
  "mcpServers": {
    "figma-docs": {
      "command": "/Users/yourname/figma-mcp-server/venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/Users/yourname/figma-mcp-server",
      "env": {
        "OPENAI_API_KEY": "sk-your-actual-api-key-here",
        "PYTHONPATH": "/Users/yourname/figma-mcp-server"
      }
    }
  }
}
```

## Available Tools

### mcp_search
Search documentation and code examples:
```
"figma.createRectangle"
"how to save plugin data"
"ui.postMessage examples"
```

### mcp_expand
Get full content from search results:
```
mcp_expand("result-id")
```

### mcp_health
Check database status and search capabilities

## Database Contents

- 1,014 documentation pages
- 892 official Figma API pages
- 316 community plugin repositories
- 1,841 code example chunks
- 3,135 semantic search embeddings

## Project Structure

```
figma-mcp-server/
├── src/
│   ├── mcp_server.py           # Main MCP server
│   ├── search_engine.py        # Search with semantic/keyword fallback
│   ├── expand_engine.py        # Content expansion
│   ├── cross_linker.py         # Links between docs and examples
│   └── preview_generator.py    # Smart content previews
├── config/query_aliases.yaml   # Search term mappings
├── meta.db                     # SQLite database (57MB)
├── requirements.txt            # Python dependencies
└── setup.sh                   # Installation script
```

## Search Features

- Semantic search with OpenAI embeddings
- Keyword search fallback
- Automatic API symbol detection
- Cross-references between official docs and community examples
- Smart content previews with code highlighting

## Requirements

- Python 3.8+
- OpenAI API key
- SQLite (included)

## Troubleshooting

### Problem: "spawn EACCES" error in Cursor
**Cause:** Path contains spaces or special characters
**Solution:** Move the project to a path without spaces:
```bash
# If your path has spaces like "/Users/name/My Projects/figma-mcp-server"
# Move it to "/Users/name/figma-mcp-server"
mv "/Users/name/My Projects/figma-mcp-server" "/Users/name/figma-mcp-server"
```

### Problem: "Database connection failed"
**Cause:** Incorrect database path configuration
**Solution:** Use absolute paths in your Cursor MCP config:
```json
{
  "command": "/absolute/path/to/figma-mcp-server/venv/bin/python",
  "cwd": "/absolute/path/to/figma-mcp-server",
  "env": {
    "PYTHONPATH": "/absolute/path/to/figma-mcp-server"
  }
}
```

### Problem: OpenAI API key not working
**Cause:** Invalid or missing API key
**Solution:** 
1. Get a new key from https://platform.openai.com/api-keys
2. Make sure it starts with `sk-`
3. Check your OpenAI account has credits

## License

MIT License. All community code examples maintain their original MIT licenses.
