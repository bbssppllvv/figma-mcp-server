# Contributing to Figma Documentation MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## 🚀 Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/figma-documentation-crawler.git
   cd figma-documentation-crawler
   ```
3. **Set up the development environment**:
   ```bash
   ./setup.sh
   ```

## 🛠️ Development Setup

### Prerequisites
- Python 3.8+
- Git
- OpenAI API key (for testing semantic search)

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-api-key-here"  # Optional but recommended
```

### Testing Your Changes
```bash
# Test MCP server import
python -c "import src.mcp_server; print('✅ Import successful')"

# Test the server manually
python -m src.mcp_server

# Test with MCP client (if available)
# Follow Cursor integration instructions in README.md
```

## 📝 Making Changes

### Code Style
- Follow PEP 8 Python style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small

### Commit Messages
Use clear, descriptive commit messages:
```
feat: add new search functionality
fix: resolve database connection issue
docs: update README with new examples
refactor: improve search engine performance
```

### Branch Naming
- `feature/description` - for new features
- `fix/description` - for bug fixes
- `docs/description` - for documentation updates

## 🔍 Areas for Contribution

### High Priority
- **Performance improvements** - optimize search algorithms
- **Error handling** - improve robustness and error messages
- **Documentation** - add more examples and use cases
- **Testing** - add unit tests and integration tests

### Medium Priority
- **New search features** - additional query types or filters
- **Database optimization** - improve query performance
- **Configuration options** - more customizable behavior
- **Logging improvements** - better debugging information

### Low Priority
- **UI improvements** - better preview formatting
- **Additional integrations** - support for other editors
- **Caching mechanisms** - reduce API calls
- **Monitoring tools** - health checks and metrics

## 🧪 Testing Guidelines

### Manual Testing
1. Test basic search functionality:
   ```python
   # Test API symbol detection
   "figma.createRectangle"
   
   # Test natural language queries
   "how to save user data in plugin"
   
   # Test expansion functionality
   # Use IDs from search results
   ```

2. Test error conditions:
   - Missing OpenAI API key
   - Invalid database path
   - Malformed queries

### Automated Testing
- Add tests for new functionality
- Ensure existing tests pass
- Test with multiple Python versions (3.8-3.12)

## 📋 Pull Request Process

1. **Create a feature branch** from `main`
2. **Make your changes** with clear, focused commits
3. **Test thoroughly** - both manual and automated testing
4. **Update documentation** if needed
5. **Submit a pull request** with:
   - Clear description of changes
   - Reference to any related issues
   - Screenshots or examples if applicable

### Pull Request Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Refactoring

## Testing
- [ ] Manual testing completed
- [ ] Automated tests pass
- [ ] No breaking changes

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated if needed
- [ ] No sensitive information in code
```

## 🐛 Reporting Issues

### Bug Reports
Include:
- **Environment details** (OS, Python version, MCP version)
- **Steps to reproduce** the issue
- **Expected vs actual behavior**
- **Error messages** or logs
- **Minimal example** if possible

### Feature Requests
Include:
- **Use case description** - why is this needed?
- **Proposed solution** - how should it work?
- **Alternatives considered** - other approaches
- **Additional context** - examples, mockups, etc.

## 📚 Resources

- [MCP Protocol Documentation](https://modelcontextprotocol.io/)
- [Figma Plugin API Docs](https://www.figma.com/plugin-docs/)
- [OpenAI API Documentation](https://platform.openai.com/docs/)
- [Python Style Guide (PEP 8)](https://pep8.org/)

## 🤝 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Maintain a welcoming environment

## 📞 Getting Help

- **GitHub Issues** - for bugs and feature requests
- **GitHub Discussions** - for questions and general discussion
- **Documentation** - check README.md and code comments

Thank you for contributing to make this project better! 🎉
