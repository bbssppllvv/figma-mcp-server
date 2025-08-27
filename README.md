# Figma Documentation MCP Server

A production-ready MCP (Model Context Protocol) server for searching Figma Plugin API documentation with semantic search capabilities.

## ✨ Features

- **🔍 Semantic Search**: Natural language queries with OpenAI embeddings
- **🎯 API Symbol Detection**: Automatic detection of Figma API methods
- **🔗 Cross-linking**: Links between official docs and community examples  
- **📖 Smart Expansion**: Auto-detect and expand pages or chunks
- **⚡ Fast Fallback**: Keyword search when semantic search unavailable
- **🎨 Rich Previews**: Context-aware content previews

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- OpenAI API key (recommended for best search quality)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd figma-documentation-crawler
```

2. **Run setup script**
```bash
chmod +x setup.sh
./setup.sh
```

3. **Set OpenAI API key** (optional but recommended)
```bash
export OPENAI_API_KEY="your-api-key-here"
```

4. **Test the server**
```bash
python -m src.mcp_server
```

### Cursor Integration

Add to your Cursor MCP configuration (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "figma-docs": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/figma-documentation-crawler",
      "env": {
        "OPENAI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## 📁 Project Structure

```
figma-documentation-crawler/
├── src/                          # Source code
│   ├── mcp_server.py            # Main MCP server
│   ├── search_engine.py         # Search functionality  
│   ├── expand_engine.py         # Content expansion
│   ├── cross_linker.py          # Cross-referencing
│   ├── preview_generator.py     # Preview generation
│   └── query_normalizer.py      # Query processing
├── config/
│   └── query_aliases.yaml       # Search aliases
├── meta.db                      # SQLite database
├── requirements.txt             # Dependencies
├── setup.sh                     # Setup script
└── mcp-start.sh                 # Launch script
```

## 🔧 MCP Tools

The server provides these tools for Cursor:

### `mcp_search`
Unified smart search with semantic capabilities
```python
# Natural language queries
"how to save user data in plugin"
"export PNG from plugin"

# API symbols  
"figma.createRectangle"
"ui.postMessage"
```

### `mcp_expand` 
Expand full content from search results
```python
# Auto-detects page vs chunk
mcp_expand("page-id-or-chunk-id")
```

### `mcp_health`
Check database status and search engine health

## 📊 Database Content

- **1,014 pages** total documentation
- **892 official** Figma documentation pages
- **316 community** plugin examples from GitHub
- **1,841 chunks** of community content
- **3,135 embeddings** for semantic search

**Coverage includes:**
- Plugin API, Widget API, REST API
- Community plugins and examples
- Code samples and tutorials

## 🔍 Search Capabilities

### Semantic Search (with OpenAI API key)
- Natural language understanding
- Context-aware results
- Cross-referencing between sections

### Keyword Search (fallback)
- Fast text matching
- API symbol detection
- Regex pattern support

### Smart Features
- Auto-detection of API symbols
- Cross-links between official docs and community examples
- Confidence scoring and result ranking
- Multiple search strategies with fallback

## ⚙️ Configuration

### Environment Variables
- `OPENAI_API_KEY`: For semantic search (optional)
- `FIGMA_DB`: Database path (defaults to `./meta.db`)

### Search Aliases
Customize search behavior in `config/query_aliases.yaml`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Figma team for comprehensive API documentation
- MCP protocol by Anthropic
- OpenAI for embedding models
- Community plugin developers for examples
