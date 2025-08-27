#!/usr/bin/env python3
"""
Cross-Linker для MCP Figma Documentation
Создает связи между official docs и community examples
"""

import re
import sqlite3
from typing import List, Dict, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


class CrossLinker:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._api_symbol_cache = {}
        self._community_usage_cache = {}
    
    def extract_api_symbols_from_content(self, content: str) -> Set[str]:
        """Извлекает API символы из контента"""
        if not content:
            return set()
        
        # Кэшируем результаты для производительности
        content_hash = hash(content[:500])  # Используем первые 500 символов для хэша
        if content_hash in self._api_symbol_cache:
            return self._api_symbol_cache[content_hash]
        
        patterns = [
            r'\bfigma\.[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*',  # figma.createRectangle
            r'\b[A-Z][A-Za-z0-9]*Node\b',  # RectangleNode, TextNode
            r'\b[A-Z][A-Za-z0-9]*Event\b',  # SelectionChangeEvent
            r'\bclientStorage\.[a-zA-Z]+',  # clientStorage.setAsync
            r'\bui\.[a-zA-Z]+',  # ui.postMessage
        ]
        
        symbols = set()
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            symbols.update(matches)
        
        # Нормализуем символы
        normalized_symbols = set()
        for symbol in symbols:
            # Убираем дубликаты с разным регистром
            normalized = symbol.lower()
            if 'figma.' in normalized:
                normalized_symbols.add(symbol)
            elif any(suffix in normalized for suffix in ['node', 'event', 'storage', 'ui.']):
                normalized_symbols.add(symbol)
        
        self._api_symbol_cache[content_hash] = normalized_symbols
        return normalized_symbols
    
    def find_community_usage(self, api_symbol: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Находит примеры использования API символа в community репозиториях"""
        cache_key = f"{api_symbol}_{limit}"
        if cache_key in self._community_usage_cache:
            return self._community_usage_cache[cache_key]
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Создаем варианты поиска для символа
            search_variants = self._create_search_variants(api_symbol)
            
            examples = []
            for variant in search_variants:
                cursor.execute("""
                    SELECT c.chunk_id, c.text, p.url, p.title
                    FROM chunks c
                    JOIN pages p ON p.id = c.page_id
                    WHERE p.section = 'community_plugin' 
                      AND c.text LIKE '%' || ? || '%'
                    ORDER BY 
                        CASE WHEN c.text LIKE '%figma.%' THEN 1 ELSE 2 END,
                        LENGTH(c.text) ASC
                    LIMIT ?
                """, (variant, limit))
                
                rows = cursor.fetchall()
                if rows:  # Если нашли результаты, прекращаем поиск
                    for row in rows:
                        examples.append({
                            "chunk_id": row['chunk_id'],
                            "url": row['url'],
                            "title": row['title'] or "Community Example",
                            "snippet": self._extract_relevant_snippet(row['text'], api_symbol),
                            "confidence": self._calculate_usage_confidence(row['text'], api_symbol)
                        })
                    break
            
            conn.close()
            
            # Сортируем по confidence
            examples.sort(key=lambda x: x['confidence'], reverse=True)
            result = examples[:limit]
            
            self._community_usage_cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Error finding community usage for {api_symbol}: {e}")
            return []
    
    def find_official_documentation(self, api_symbol: str) -> Optional[Dict[str, Any]]:
        """Находит официальную документацию для API символа"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Ищем в официальной документации
            search_variants = self._create_search_variants(api_symbol)
            
            for variant in search_variants:
                cursor.execute("""
                    SELECT p.id, p.title, p.url, c.text
                    FROM pages p
                    JOIN chunks c ON c.page_id = p.id
                    WHERE p.source = 'official' 
                      AND (p.title LIKE '%' || ? || '%' OR c.text LIKE '%' || ? || '%')
                    ORDER BY 
                        CASE WHEN p.title LIKE '%' || ? || '%' THEN 1 ELSE 2 END,
                        CASE WHEN c.text LIKE '%figma.' || ? || '%' THEN 1 ELSE 2 END
                    LIMIT 1
                """, (variant, variant, variant, variant))
                
                row = cursor.fetchone()
                if row:
                    conn.close()
                    return {
                        "page_id": row['id'],
                        "title": row['title'],
                        "url": row['url'],
                        "snippet": self._extract_relevant_snippet(row['text'], api_symbol)
                    }
            
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"Error finding official docs for {api_symbol}: {e}")
            return None
    
    def add_cross_links(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Добавляет cross-links между результатами
        
        Args:
            results: Список результатов поиска
            query: Исходный поисковый запрос
            
        Returns:
            Обогащенные результаты с cross-links
        """
        if not results:
            return results
        
        # Собираем все API символы из результатов
        all_api_symbols = set()
        official_results = []
        community_results = []
        
        for result in results:
            content = result.get('text', result.get('snippet', ''))
            symbols = self.extract_api_symbols_from_content(content)
            all_api_symbols.update(symbols)
            
            # Разделяем результаты по типам
            if result.get('section') == 'plugin' or result.get('source_type') == 'official_docs':
                official_results.append(result)
            elif result.get('section') == 'community_plugin':
                community_results.append(result)
        
        # Добавляем cross-links для official результатов
        for result in official_results:
            content = result.get('text', result.get('snippet', ''))
            symbols = self.extract_api_symbols_from_content(content)
            
            community_examples = []
            for symbol in symbols:
                examples = self.find_community_usage(symbol, limit=2)
                community_examples.extend(examples)
            
            if community_examples:
                # Убираем дубликаты и сортируем по confidence
                unique_examples = {}
                for ex in community_examples:
                    key = ex['chunk_id']
                    if key not in unique_examples or ex['confidence'] > unique_examples[key]['confidence']:
                        unique_examples[key] = ex
                
                sorted_examples = sorted(unique_examples.values(), 
                                       key=lambda x: x['confidence'], reverse=True)[:2]
                
                result['cross_links'] = {
                    "type": "community_examples",
                    "title": "💻 Community Usage Examples",
                    "examples": sorted_examples
                }
        
        # Добавляем cross-links для community результатов
        for result in community_results:
            content = result.get('text', result.get('snippet', ''))
            symbols = self.extract_api_symbols_from_content(content)
            
            official_docs = []
            for symbol in symbols:
                doc = self.find_official_documentation(symbol)
                if doc:
                    official_docs.append(doc)
            
            if official_docs:
                # Убираем дубликаты
                unique_docs = {}
                for doc in official_docs:
                    key = doc['page_id']
                    if key not in unique_docs:
                        unique_docs[key] = doc
                
                result['cross_links'] = {
                    "type": "official_documentation", 
                    "title": "📚 Official Documentation",
                    "docs": list(unique_docs.values())[:2]
                }
        
        return results
    
    def _create_search_variants(self, api_symbol: str) -> List[str]:
        """Создает варианты поиска для API символа"""
        variants = [api_symbol]
        
        # Убираем префикс figma. если есть
        if api_symbol.startswith("figma."):
            clean_symbol = api_symbol[6:]
            variants.append(clean_symbol)
            
            # Для вложенных API (figma.variables.setValueForMode -> setValueForMode)
            if "." in clean_symbol:
                method_name = clean_symbol.split(".")[-1]
                variants.append(method_name)
        
        # Добавляем case-insensitive варианты
        variants.extend([v.lower() for v in variants])
        
        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_variants = []
        for variant in variants:
            if variant not in seen and len(variant) > 2:
                seen.add(variant)
                unique_variants.append(variant)
        
        return unique_variants
    
    def _extract_relevant_snippet(self, text: str, api_symbol: str, max_length: int = 150) -> str:
        """Извлекает релевантный snippet с API символом"""
        if not text or not api_symbol:
            return text[:max_length] if text else ""
        
        # Ищем предложение или строку с API символом
        lines = text.split('\n')
        for line in lines:
            if api_symbol.lower() in line.lower():
                # Берем эту строку и немного контекста
                line_idx = lines.index(line)
                start_idx = max(0, line_idx - 1)
                end_idx = min(len(lines), line_idx + 2)
                
                context_lines = lines[start_idx:end_idx]
                snippet = '\n'.join(context_lines).strip()
                
                if len(snippet) <= max_length:
                    return snippet
                else:
                    return snippet[:max_length] + '...'
        
        # Fallback: просто обрезаем текст
        return text[:max_length] + ('...' if len(text) > max_length else '')
    
    def _calculate_usage_confidence(self, text: str, api_symbol: str) -> float:
        """Вычисляет уверенность в релевантности примера"""
        if not text or not api_symbol:
            return 0.0
        
        text_lower = text.lower()
        symbol_lower = api_symbol.lower()
        
        confidence = 0.0
        
        # Базовая уверенность за наличие символа
        if symbol_lower in text_lower:
            confidence += 0.5
        
        # Бонус за контекст использования
        usage_indicators = ['const', 'let', 'var', '=', 'await', 'async', 'function']
        for indicator in usage_indicators:
            if indicator in text_lower:
                confidence += 0.1
        
        # Бонус за примеры кода
        if any(pattern in text for pattern in ['```', 'const ', 'let ', 'function']):
            confidence += 0.2
        
        # Штраф за слишком короткий или длинный текст
        if len(text) < 50:
            confidence -= 0.2
        elif len(text) > 2000:
            confidence -= 0.1
        
        return min(1.0, max(0.0, confidence))


if __name__ == "__main__":
    # Тестирование
    import os
    
    db_path = os.getenv("DB_PATH", "data/meta.db")
    linker = CrossLinker(db_path)
    
    # Тест извлечения API символов
    test_content = """
    const rect = figma.createRectangle()
    rect.resize(100, 100)
    figma.ui.postMessage({type: 'created'})
    """
    
    symbols = linker.extract_api_symbols_from_content(test_content)
    print("API Symbols found:", symbols)
    
    # Тест поиска community usage
    if symbols:
        symbol = list(symbols)[0]
        usage = linker.find_community_usage(symbol)
        print(f"Community usage for {symbol}:", len(usage), "examples")
