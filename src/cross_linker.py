#!/usr/bin/env python3
"""
Cross-Linker for MCP Figma Documentation
Creates links between official docs and community examples
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
        """Extracts API symbols from content"""
        if not content:
            return set()
        
        # Cache results for performance
        content_hash = hash(content[:500])  # Use first 500 characters for hash
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
        
        # Normalize symbols
        normalized_symbols = set()
        for symbol in symbols:
            # Remove duplicates with different case
            normalized = symbol.lower()
            if 'figma.' in normalized:
                normalized_symbols.add(symbol)
            elif any(suffix in normalized for suffix in ['node', 'event', 'storage', 'ui.']):
                normalized_symbols.add(symbol)
        
        self._api_symbol_cache[content_hash] = normalized_symbols
        return normalized_symbols
    
    def find_community_usage(self, api_symbol: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Finds API symbol usage examples in community repositories"""
        cache_key = f"{api_symbol}_{limit}"
        if cache_key in self._community_usage_cache:
            return self._community_usage_cache[cache_key]
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Create search variants for symbol
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
                if rows:  # If found results, stop searching
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
            
            # Sort by confidence
            examples.sort(key=lambda x: x['confidence'], reverse=True)
            result = examples[:limit]
            
            self._community_usage_cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Error finding community usage for {api_symbol}: {e}")
            return []
    
    def find_official_documentation(self, api_symbol: str) -> Optional[Dict[str, Any]]:
        """Finds official documentation for API symbol"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Search in official documentation
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
        Adds cross-links between results
        
        Args:
            results: List of search results
            query: Original search query
            
        Returns:
            Enriched results with cross-links
        """
        if not results:
            return results
        
        # Collect all API symbols from results
        all_api_symbols = set()
        official_results = []
        community_results = []
        
        for result in results:
            content = result.get('text', result.get('snippet', ''))
            symbols = self.extract_api_symbols_from_content(content)
            all_api_symbols.update(symbols)
            
            # Separate results by types
            if result.get('section') == 'plugin' or result.get('source_type') == 'official_docs':
                official_results.append(result)
            elif result.get('section') == 'community_plugin':
                community_results.append(result)
        
        # Add cross-links for official results
        for result in official_results:
            content = result.get('text', result.get('snippet', ''))
            symbols = self.extract_api_symbols_from_content(content)
            
            community_examples = []
            for symbol in symbols:
                examples = self.find_community_usage(symbol, limit=2)
                community_examples.extend(examples)
            
            if community_examples:
                # Remove duplicates and sort by confidence
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
        
        # Add cross-links for community results
        for result in community_results:
            content = result.get('text', result.get('snippet', ''))
            symbols = self.extract_api_symbols_from_content(content)
            
            official_docs = []
            for symbol in symbols:
                doc = self.find_official_documentation(symbol)
                if doc:
                    official_docs.append(doc)
            
            if official_docs:
                # Remove duplicates
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
        """Creates search variants for API symbol"""
        variants = [api_symbol]
        
        # Remove figma. prefix if present
        if api_symbol.startswith("figma."):
            clean_symbol = api_symbol[6:]
            variants.append(clean_symbol)
            
            # For nested API (figma.variables.setValueForMode -> setValueForMode)
            if "." in clean_symbol:
                method_name = clean_symbol.split(".")[-1]
                variants.append(method_name)
        
        # Add case-insensitive variants
        variants.extend([v.lower() for v in variants])
        
        # Remove duplicates, preserving order
        seen = set()
        unique_variants = []
        for variant in variants:
            if variant not in seen and len(variant) > 2:
                seen.add(variant)
                unique_variants.append(variant)
        
        return unique_variants
    
    def _extract_relevant_snippet(self, text: str, api_symbol: str, max_length: int = 150) -> str:
        """Extracts relevant snippet with API symbol"""
        if not text or not api_symbol:
            return text[:max_length] if text else ""
        
        # Find sentence or line with API symbol
        lines = text.split('\n')
        for line in lines:
            if api_symbol.lower() in line.lower():
                # Take this line and some context
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
        """Calculates confidence in example relevance"""
        if not text or not api_symbol:
            return 0.0
        
        text_lower = text.lower()
        symbol_lower = api_symbol.lower()
        
        confidence = 0.0
        
        # Base confidence for symbol presence
        if symbol_lower in text_lower:
            confidence += 0.5
        
        # Bonus for usage context
        usage_indicators = ['const', 'let', 'var', '=', 'await', 'async', 'function']
        for indicator in usage_indicators:
            if indicator in text_lower:
                confidence += 0.1
        
        # Bonus for code examples
        if any(pattern in text for pattern in ['```', 'const ', 'let ', 'function']):
            confidence += 0.2
        
        # Penalty for too short or too long text
        if len(text) < 50:
            confidence -= 0.2
        elif len(text) > 2000:
            confidence -= 0.1
        
        return min(1.0, max(0.0, confidence))


if __name__ == "__main__":
    # Testing
    import os
    
    db_path = os.getenv("DB_PATH", "data/meta.db")
    linker = CrossLinker(db_path)
    
    # Test API symbol extraction
    test_content = """
    const rect = figma.createRectangle()
    rect.resize(100, 100)
    figma.ui.postMessage({type: 'created'})
    """
    
    symbols = linker.extract_api_symbols_from_content(test_content)
    print("API Symbols found:", symbols)
    
    # Test community usage search
    if symbols:
        symbol = list(symbols)[0]
        usage = linker.find_community_usage(symbol)
        print(f"Community usage for {symbol}:", len(usage), "examples")
