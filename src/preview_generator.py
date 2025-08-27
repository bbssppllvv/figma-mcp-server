#!/usr/bin/env python3
"""
Smart Preview Generator для MCP Figma Documentation
Создает умные превью с учетом запроса и контекста
"""

import re
from typing import List, Optional, Tuple


def extract_code_blocks(text: str) -> List[str]:
    """Извлекает блоки кода из текста"""
    # Ищем блоки кода в разных форматах
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
    """Разбивает текст на предложения"""
    # Улучшенная логика разбивки на предложения
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    
    # Фильтруем слишком короткие предложения
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def extract_api_symbols_from_text(text: str) -> List[str]:
    """Извлекает API символы из текста"""
    pattern = r'\bfigma\.[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*'
    return list(set(re.findall(pattern, text, re.IGNORECASE)))


def calculate_sentence_relevance_score(sentence: str, query_words: List[str]) -> float:
    """Вычисляет релевантность предложения к запросу"""
    sentence_lower = sentence.lower()
    score = 0.0
    
    # Бонус за содержание ключевых слов запроса
    for word in query_words:
        if word in sentence_lower:
            score += 10
            # Дополнительный бонус если слово в начале предложения
            if sentence_lower.startswith(word):
                score += 5
    
    # Бонус за содержание API методов
    api_symbols = extract_api_symbols_from_text(sentence)
    if api_symbols:
        score += 8 * len(api_symbols)
    
    # Бонус за содержание полезных слов
    useful_words = [
        'create', 'export', 'load', 'set', 'get', 'add', 'remove', 'update',
        'async', 'await', 'function', 'method', 'property', 'example'
    ]
    for word in useful_words:
        if word in sentence_lower:
            score += 2
    
    # Штраф за технические детали в начале
    technical_starts = [
        'set to null', 'supported on:', 'info', 'this api is only', 
        'value must be', 'deprecated', 'warning', 'note:'
    ]
    for start in technical_starts:
        if sentence_lower.startswith(start):
            score -= 5
    
    # Штраф за слишком длинные предложения
    if len(sentence) > 300:
        score -= 3
    
    # Бонус за средние предложения (не слишком короткие, не слишком длинные)
    if 50 <= len(sentence) <= 200:
        score += 2
    
    return score


def format_code_preview(code_block: str, max_length: int) -> str:
    """Форматирует превью кодового блока"""
    # Убираем лишние пробелы и переносы
    code_block = re.sub(r'\n\s*\n', '\n', code_block.strip())
    
    if len(code_block) <= max_length:
        return code_block
    
    # Пытаемся найти хорошую точку обрезки (конец строки)
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
    """Умная обрезка текста по словам и предложениям"""
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    
    # Пытаемся найти конец предложения
    sentence_ends = ['.', '!', '?']
    best_end = -1
    
    for end_char in sentence_ends:
        pos = truncated.rfind(end_char + ' ')
        if pos > max_length * 0.6:  # Не слишком короткая обрезка
            best_end = max(best_end, pos + 1)
    
    if best_end > 0:
        return text[:best_end].strip()
    
    # Обрезаем по словам
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    
    return truncated.strip() + '…'


def create_smart_preview(text: str, query: str = "", max_length: int = 250) -> str:
    """
    Создает умный preview с учетом запроса и контекста
    
    Args:
        text: Исходный текст
        query: Поисковый запрос для релевантности
        max_length: Максимальная длина preview
    
    Returns:
        Умный preview текста
    """
    # Очищаем текст
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) <= max_length:
        return text
    
    # Извлекаем ключевые слова из запроса
    query_words = [word.lower() for word in query.split() if len(word) > 2]
    
    # 1. Приоритет: Поиск кодового блока с API методами
    code_blocks = extract_code_blocks(text)
    for code_block in code_blocks:
        if any(api in code_block.lower() for api in ['figma.', 'async', 'await', 'function']):
            if any(word in code_block.lower() for word in query_words) or not query_words:
                return format_code_preview(code_block, max_length)
    
    # 2. Поиск наиболее релевантного предложения
    sentences = split_into_sentences(text)
    
    if sentences:
        best_sentence = None
        best_score = -1
        
        for i, sentence in enumerate(sentences):
            score = calculate_sentence_relevance_score(sentence, query_words)
            
            # Бонус за позицию (первые предложения важнее)
            if i == 0:
                score += 5
            elif i == 1:
                score += 3
            
            if score > best_score:
                best_score = score
                best_sentence = sentence
        
        # Если нашли хорошее предложение, используем его
        if best_sentence and best_score > 0:
            return truncate_smart(best_sentence, max_length)
    
    # 3. Fallback: Ищем абзац с ключевыми словами
    paragraphs = text.split('\n\n')
    for para in paragraphs:
        para = para.strip()
        if len(para) < 50:  # Пропускаем заголовки
            continue
            
        para_lower = para.lower()
        if query_words and any(word in para_lower for word in query_words):
            return truncate_smart(para, max_length)
        
        # Если есть API методы, тоже хорошо
        if 'figma.' in para_lower:
            return truncate_smart(para, max_length)
    
    # 4. Последний fallback: начало текста
    return truncate_smart(text, max_length)


def create_preview_with_context(text: str, query: str = "", max_length: int = 250, 
                               source_type: str = "unknown") -> dict:
    """
    Создает расширенный preview с контекстной информацией
    
    Returns:
        dict с preview, metadata и hints
    """
    preview = create_smart_preview(text, query, max_length)
    
    # Извлекаем дополнительную информацию
    api_symbols = extract_api_symbols_from_text(text)
    code_blocks = extract_code_blocks(text)
    
    # Определяем тип контента
    content_type = "text"
    if code_blocks:
        content_type = "code"
    elif api_symbols:
        content_type = "api_reference"
    
    return {
        "preview": preview,
        "content_type": content_type,
        "api_symbols": api_symbols[:3],  # Топ 3 API символа
        "has_code": len(code_blocks) > 0,
        "estimated_relevance": _estimate_relevance(text, query),
        "source_type": source_type
    }


def _estimate_relevance(text: str, query: str) -> str:
    """Оценивает релевантность текста к запросу"""
    if not query:
        return "unknown"
    
    query_words = [word.lower() for word in query.split() if len(word) > 2]
    text_lower = text.lower()
    
    # Считаем совпадения
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


# Обратная совместимость
def create_preview(text: str, max_length: int = 250) -> str:
    """Обратная совместимость - вызывает create_smart_preview"""
    return create_smart_preview(text, "", max_length)


if __name__ == "__main__":
    # Тестирование
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
