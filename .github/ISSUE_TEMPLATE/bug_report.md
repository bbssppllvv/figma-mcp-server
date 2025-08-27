---
name: Bug report
about: Create a report to help us improve
title: '[BUG] '
labels: bug
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Set up environment with '...'
2. Run command '....'
3. Execute query '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Error output**
If applicable, add error messages or logs to help explain your problem.

```
Paste error output here
```

**Environment (please complete the following information):**
 - OS: [e.g. macOS 14.0, Ubuntu 22.04]
 - Python version: [e.g. 3.9.7]
 - MCP version: [e.g. 1.13.0]
 - OpenAI API key configured: [Yes/No]

**Query details**
If the issue is related to search:
- Query text: [e.g. "figma.createRectangle"]
- Search section: [e.g. auto, official, community_plugin]
- Expected results vs actual results

**Additional context**
Add any other context about the problem here.

**Database info**
If relevant, include output from health check:
```
# Run this command and paste output
python -c "
import src.mcp_server
# Add any relevant database info
"
```
