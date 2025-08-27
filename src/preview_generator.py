#!/usr/bin/env python3
"""
Smart Preview Generator for MCP Figma Documentation
Creates smart previews considering query and context
"""

import re
from typing import List, Optional, Tuple


def extract_code_blocks(text: str) -> List[str]:
    """Extracts code blocks from text"""
    # Find code blocks in different formats
    patterns = [
        r'```[\w]*\n(.*?)\n```',  # Markdown code blocks
        r'`([^`\n]+)`',           # Inline code
        r'^\s*([a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*[{;])',  # Function definitions
        r'^\s*(const|let|var|function)\s+([^=\n]+)',  # JS declarations
        r'^\s*(figma\.[a-zA-Z][a-zA-Z0-9_.]*)',  # Figma API calls
    ]
    
    code_blocks = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
        for match in matches:
            if isinstance(match, tuple):
                code_blocks.extend([m for m in match if m.strip()])
            else:
                code_blocks.append(match.strip())
    
    return [block for block in code_blocks if len(block) > 10]


def split_into_sentences(text: str) -> List[str]:
    """Splits text into sentences"""
    # Improved sentence splitting logic
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    
    # Filter too short sentences
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def extract_api_symbols_from_text(text: str) -> List[str]:
    """Extracts API symbols from text"""
    pattern = r'\bfigma\.[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*'
    return list(set(re.findall(pattern, text, re.IGNORECASE)))


def calculate_sentence_relevance_score(sentence: str, query_words: List[str]) -> float:
    """Calculates sentence relevance to query"""
    sentence_lower = sentence.lower()
    score = 0.0
    
    # Bonus for containing query keywords
    for word in query_words:
        if word in sentence_lower:
            score += 10
            # Additional bonus if word is at sentence start
            if sentence_lower.startswith(word):
                score += 5
    
    # Bonus for containing API methods
    api_symbols = extract_api_symbols_from_text(sentence)
    if api_symbols:
        score += 8 * len(api_symbols)
    
    # Bonus for containing useful words
    useful_words = [
        'create', 'export', 'load', 'set', 'get', 'add', 'remove', 'update',
        'async', 'await', 'function', 'method', 'property', 'example'
    ]
    for word in useful_words:
        if word in sentence_lower:
            score += 2
    
    # Penalty for technical details at start
    technical_starts = [
        'set to null', 'supported on:', 'info', 'this api is only', 
        'value must be', 'deprecated', 'warning', 'note:'
    ]
    for start in technical_starts:
        if sentence_lower.startswith(start):
            score -= 5
    
    # Penalty for too long sentences
    if len(sentence) > 300:
        score -= 3
    
    # Bonus for medium sentences (not too short, not too long)
    if 50 <= len(sentence) <= 200:
        score += 2
    
    return score


def format_code_preview(code_block: str, max_length: int) -> str:
    """Formats code block preview"""
    # Remove extra spaces and line breaks
    code_block = re.sub(r'\n\s*\n', '\n', code_block.strip())
    
    if len(code_block) <= max_length:
        return code_block
    
    # Try to find good truncation point (end of line)
    lines = code_block.split('\n')
    result_lines = []
    current_length = 0
    
    for line in lines:
        if current_length + len(line) + 1 > max_length * 0.8:
            break
        result_lines.append(line)
        current_length += len(line) + 1
    
    if result_lines:
        return '\n'.join(result_lines) + '\n...'
    else:
        return code_block[:max_length] + '...'


def truncate_smart(text: str, max_length: int) -> str:
    """Smart text truncation by words and sentences"""
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    
    # Try to find end of sentence
    sentence_ends = ['.', '!', '?']
    best_end = -1
    
    for end_char in sentence_ends:
        pos = truncated.rfind(end_char + ' ')
        if pos > max_length * 0.6:  # Not too short truncation
            best_end = max(best_end, pos + 1)
    
    if best_end > 0:
        return text[:best_end].strip()
    
    # Truncate by words
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    
    return truncated.strip() + '…'


def create_smart_preview(text: str, query: str = "", max_length: int = 250) -> str:
    """
    Creates smart preview considering query and context
    
    Args:
        text: Source text
        query: Search query for relevance
        max_length: Maximum preview length
    
    Returns:
        Smart text preview
    """
    # Clean text
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) <= max_length:
        return text
    
    # Extract keywords from query
    query_words = [word.lower() for word in query.split() if len(word) > 2]
    
    # 1. Priority: Find code block with API methods
    code_blocks = extract_code_blocks(text)
    for code_block in code_blocks:
        if any(api in code_block.lower() for api in ['figma.', 'async', 'await', 'function']):
            if any(word in code_block.lower() for word in query_words) or not query_words:
                return format_code_preview(code_block, max_length)
    
    # 2. Find most relevant sentence
    sentences = split_into_sentences(text)
    
    if sentences:
        best_sentence = None
        best_score = -1
        
        for i, sentence in enumerate(sentences):
            score = calculate_sentence_relevance_score(sentence, query_words)
            
            # Bonus for position (first sentences are more important)
            if i == 0:
                score += 5
            elif i == 1:
                score += 3
            
            if score > best_score:
                best_score = score
                best_sentence = sentence
        
        # If found good sentence, use it
        if best_sentence and best_score > 0:
            return truncate_smart(best_sentence, max_length)
    
    # 3. Fallback: Find paragraph with keywords
    paragraphs = text.split('\n\n')
    for para in paragraphs:
        para = para.strip()
        if len(para) < 50:  # Skip headers
            continue
            
        para_lower = para.lower()
        if query_words and any(word in para_lower for word in query_words):
            return truncate_smart(para, max_length)
        
        # If has API methods, also good
        if 'figma.' in para_lower:
            return truncate_smart(para, max_length)
    
    # 4. Last fallback: beginning of text
    return truncate_smart(text, max_length)


def create_preview_with_context(text: str, query: str = "", max_length: int = 250, 
                               source_type: str = "unknown") -> dict:
    """
    Creates extended preview with contextual information
    
    Returns:
        dict with preview, metadata and hints
    """
    preview = create_smart_preview(text, query, max_length)
    
    # Extract additional information
    api_symbols = extract_api_symbols_from_text(text)
    code_blocks = extract_code_blocks(text)
    
    # Determine content type
    content_type = "text"
    if code_blocks:
        content_type = "code"
    elif api_symbols:
        content_type = "api_reference"
    
    return {
        "preview": preview,
        "content_type": content_type,
        "api_symbols": api_symbols[:3],  # Top 3 API symbols
        "has_code": len(code_blocks) > 0,
        "estimated_relevance": _estimate_relevance(text, query),
        "source_type": source_type
    }


def _estimate_relevance(text: str, query: str) -> str:
    """Estimates text relevance to query"""
    if not query:
        return "unknown"
    
    query_words = [word.lower() for word in query.split() if len(word) > 2]
    text_lower = text.lower()
    
    # Count matches
    matches = sum(1 for word in query_words if word in text_lower)
    api_symbols = len(extract_api_symbols_from_text(text))
    
    if matches >= len(query_words) * 0.8 and api_symbols > 0:
        return "high"
    elif matches >= len(query_words) * 0.5 or api_symbols > 0:
        return "medium"
    elif matches > 0:
        return "low"
    else:
        return "minimal"


# Backward compatibility
def create_preview(text: str, max_length: int = 250) -> str:
    """Backward compatibility - calls create_smart_preview"""
    return create_smart_preview(text, "", max_length)


if __name__ == "__main__":
    # Testing
    test_text = """
    Creating rectangles in Figma plugins is straightforward. 
    You can use the figma.createRectangle() method to create a new rectangle node.
    
    const rect = figma.createRectangle()
    rect.x = 50
    rect.y = 50
    rect.resize(200, 100)
    rect.fills = [{ type: 'SOLID', color: { r: 1, g: 0, b: 0 } }]
    
    This creates a red rectangle at position (50, 50) with dimensions 200x100.
    """
    
    print("=== Smart Preview Test ===")
    print("Query: 'create rectangle'")
    print("Preview:", create_smart_preview(test_text, "create rectangle", 150))
    print()
    
    print("=== Context Preview Test ===")
    context = create_preview_with_context(test_text, "create rectangle", 150, "official_docs")
    print("Context:", context)
