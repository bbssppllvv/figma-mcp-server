#!/usr/bin/env python3
"""
Unified Search Engine for MCP Figma Documentation
Combines semantic search, API lookup and cross-linking
"""

import sqlite3
import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple
import openai
import os

try:
    from .preview_generator import create_smart_preview, extract_api_symbols_from_text
    from .cross_linker import CrossLinker
except ImportError:
    # Fallback for direct execution
    from preview_generator import create_smart_preview, extract_api_symbols_from_text
    from cross_linker import CrossLinker

logger = logging.getLogger(__name__)


class UnifiedSearchEngine:
    def __init__(self, db_path: str, openai_client: Optional[openai.OpenAI] = None):
        self.db_path = db_path
        self.openai_client = openai_client
        self.cross_linker = CrossLinker(db_path)
        
    def get_db_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> Optional[np.ndarray]:
        """Get embedding"""
        if not self.openai_client:
            return None
        
        try:
            response = self.openai_client.embeddings.create(input=text, model=model)
            return np.array(response.data[0].embedding)
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            return None
    
    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity"""
        try:
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))
        except Exception as e:
            logger.error(f"Cosine similarity error: {e}")
            return 0.0
    
    def extract_api_symbols_from_query(self, query: str) -> List[str]:
        """Extracts API symbols from query"""
        # Simple patterns for detecting API symbols in query
        api_patterns = [
            r'\bfigma\.[a-zA-Z][a-zA-Z0-9_.]*',
            r'\b[A-Z][a-zA-Z0-9]*Node\b',
            r'\bclientStorage\b',
            r'\bui\.postMessage\b',
            r'\bshowUI\b'
        ]
        
        import re
        symbols = []
        for pattern in api_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            symbols.extend(matches)
        
        return list(set(symbols))
    
    async def semantic_search(self, query: str, section: str, top_k: int, 
                            model: str = "text-embedding-3-small") -> List[Dict[str, Any]]:
        """Semantic search"""
        query_embedding = await self.get_embedding(query, model)
        if query_embedding is None:
            return []
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Определяем фильтр в зависимости от секции
        if section == "official":
            filter_condition = "p.source = ? AND p.section = ?"
            filter_params = ("official", "plugin")
        elif section == "community_plugin":
            filter_condition = "p.section = ?"
            filter_params = ("community_plugin",)
        else:
            filter_condition = "(p.section = ? OR p.source = ?)"
            filter_params = (section, section)
        
        cursor.execute(f"""
            SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title, e.embedding
            FROM chunks c
            JOIN pages p ON p.id = c.page_id
            JOIN embeddings e ON e.chunk_id = c.chunk_id
            WHERE {filter_condition} AND e.model = ?
            LIMIT 100
        """, (*filter_params, model))
        
        candidates = []
        for row in cursor.fetchall():
            try:
                vector = np.frombuffer(row['embedding'], dtype=np.float32)
                score = self.cosine_similarity(query_embedding, vector)
                candidates.append({
                    'chunk_id': row['chunk_id'],
                    'page_id': row['page_id'],
                    'score': float(score),
                    'text': row['text'],
                    'url': row['url'],
                    'section': row['section'],
                    'title': row['title']
                })
            except Exception as e:
                logger.warning(f"Failed to process embedding for chunk {row['chunk_id']}: {e}")
                continue
        
        conn.close()
        
        # Sort by score
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:top_k]
    
    def keyword_search(self, query: str, section: str, top_k: int) -> List[Dict[str, Any]]:
        """Keyword поиск как fallback"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        if section == "official":
            cursor.execute("""
                SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title
                FROM chunks c
                JOIN pages p ON p.id = c.page_id
                WHERE p.source = ? AND p.section = ? AND c.text LIKE '%' || ? || '%'
                ORDER BY 
                    CASE WHEN c.text LIKE '%figma.%' THEN 1 ELSE 2 END,
                    LENGTH(c.text) ASC
                LIMIT ?
            """, ("official", "plugin", query, top_k))
        elif section == "community_plugin":
            cursor.execute("""
                SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title
                FROM chunks c
                JOIN pages p ON p.id = c.page_id
                WHERE p.section = ? AND c.text LIKE '%' || ? || '%'
                ORDER BY 
                    CASE WHEN c.text LIKE '%figma.%' THEN 1 ELSE 2 END,
                    LENGTH(c.text) ASC
                LIMIT ?
            """, (section, query, top_k))
        else:
            cursor.execute("""
                SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title
                FROM chunks c
                JOIN pages p ON p.id = c.page_id
                WHERE (p.section = ? OR p.source = ?) AND c.text LIKE '%' || ? || '%'
                ORDER BY 
                    CASE WHEN c.text LIKE '%figma.%' THEN 1 ELSE 2 END,
                    LENGTH(c.text) ASC
                LIMIT ?
            """, (section, section, query, top_k))
        
        candidates = []
        for row in cursor.fetchall():
            text_lower = row['text'].lower()
            q_lower = query.lower()
            score = min(text_lower.count(q_lower) / len(text_lower.split()), 1.0)
            
            candidates.append({
                'chunk_id': row['chunk_id'],
                'page_id': row['page_id'],
                'score': score,
                'text': row['text'],
                'url': row['url'],
                'section': row['section'],
                'title': row['title']
            })
        
        conn.close()
        return candidates
    
    def api_symbol_search(self, symbol: str, section: str, top_k: int) -> List[Dict[str, Any]]:
        """Поиск по API символу"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Создаем варианты поиска
        search_terms = [symbol]
        if symbol.startswith("figma."):
            clean_symbol = symbol[6:]
            search_terms.append(clean_symbol)
            if "." in clean_symbol:
                method_name = clean_symbol.split(".")[-1]
                search_terms.append(method_name)
        
        # Добавляем case-insensitive варианты
        search_terms.extend([term.lower() for term in search_terms])
        search_terms = list(set(search_terms))
        
        candidates = []
        for search_term in search_terms:
            if section == "official":
                cursor.execute("""
                    SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title
                    FROM chunks c
                    JOIN pages p ON p.id = c.page_id
                    WHERE p.source = 'official' AND p.section = 'plugin'
                      AND c.text LIKE '%' || ? || '%'
                    ORDER BY 
                        CASE WHEN c.text LIKE '%figma.%' THEN 1 ELSE 2 END,
                        LENGTH(c.text) ASC
                    LIMIT ?
                """, (search_term, top_k))
            elif section == "community_plugin":
                cursor.execute("""
                    SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title
                    FROM chunks c
                    JOIN pages p ON p.id = c.page_id
                    WHERE p.section = 'community_plugin' 
                      AND c.text LIKE '%' || ? || '%'
                    ORDER BY 
                        CASE WHEN c.text LIKE '%figma.%' THEN 1 ELSE 2 END,
                        LENGTH(c.text) ASC
                    LIMIT ?
                """, (search_term, top_k))
            
            rows = cursor.fetchall()
            if rows:  # Если нашли результаты, прекращаем поиск
                for row in rows:
                    candidates.append({
                        'chunk_id': row['chunk_id'],
                        'page_id': row['page_id'],
                        'score': 0.8,  # Высокий score для точного API поиска
                        'text': row['text'],
                        'url': row['url'],
                        'section': row['section'],
                        'title': row['title'],
                        'api_match': True
                    })
                break
        
        conn.close()
        return candidates
    
    def fuzzy_fallback_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Последний fallback - возвращает любые релевантные результаты"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Берем случайные результаты с API методами
        cursor.execute("""
            SELECT c.chunk_id, c.page_id, c.text, p.url, p.section, p.title
            FROM chunks c
            JOIN pages p ON p.id = c.page_id
            WHERE c.text LIKE '%figma.%'
            ORDER BY RANDOM()
            LIMIT ?
        """, (top_k,))
        
        candidates = []
        for row in cursor.fetchall():
            candidates.append({
                'chunk_id': row['chunk_id'],
                'page_id': row['page_id'],
                'score': 0.1,  # Низкий score для fallback
                'text': row['text'],
                'url': row['url'],
                'section': row['section'],
                'title': row['title'],
                'is_fallback': True
            })
        
        conn.close()
        return candidates
    
    async def unified_search(self, query: str, section: str = "auto", 
                           top_k: int = 5, model: str = "text-embedding-3-small") -> Dict[str, Any]:
        """
        Единый умный поиск
        
        Args:
            query: Поисковый запрос
            section: Секция поиска ('auto', 'official', 'community_plugin')
            top_k: Количество результатов
            model: Модель для embeddings
            
        Returns:
            Объединенные результаты с cross-links
        """
        all_results = []
        search_strategy = []
        
        # Определяем стратегию поиска
        api_symbols = self.extract_api_symbols_from_query(query)
        
        # Шаг 1: Семантический поиск в official
        if section in ["auto", "official"]:
            official_results = await self.semantic_search(query, "official", top_k, model)
            if official_results:
                for result in official_results:
                    result['source_type'] = 'official_docs'
                    result['search_method'] = 'semantic'
                all_results.extend(official_results)
                search_strategy.append(f"semantic_official({len(official_results)})")
        
        # Шаг 2: Fallback к community если мало результатов
        if len(all_results) < 3 and section in ["auto", "community_plugin"]:
            community_results = await self.semantic_search(query, "community_plugin", 
                                                          max(3, top_k - len(all_results)), model)
            if community_results:
                for result in community_results:
                    result['source_type'] = 'community_code'
                    result['search_method'] = 'semantic'
                all_results.extend(community_results)
                search_strategy.append(f"semantic_community({len(community_results)})")
        
        # Шаг 3: API symbol detection и поиск
        if api_symbols:
            for symbol in api_symbols[:2]:  # Ограничиваем количество символов
                api_results_official = self.api_symbol_search(symbol, "official", 2)
                api_results_community = self.api_symbol_search(symbol, "community_plugin", 2)
                
                for result in api_results_official:
                    result['source_type'] = 'api_reference'
                    result['search_method'] = 'api_symbol'
                    result['matched_symbol'] = symbol
                
                for result in api_results_community:
                    result['source_type'] = 'community_code'
                    result['search_method'] = 'api_symbol'
                    result['matched_symbol'] = symbol
                
                all_results.extend(api_results_official + api_results_community)
                if api_results_official or api_results_community:
                    search_strategy.append(f"api_symbol_{symbol}({len(api_results_official + api_results_community)})")
        
        # Шаг 4: Keyword fallback если семантический поиск не сработал
        if len(all_results) == 0:
            keyword_results = self.keyword_search(query, section if section != "auto" else "official", top_k)
            if not keyword_results and section == "auto":
                keyword_results = self.keyword_search(query, "community_plugin", top_k)
            
            for result in keyword_results:
                result['search_method'] = 'keyword'
            all_results.extend(keyword_results)
            search_strategy.append(f"keyword({len(keyword_results)})")
        
        # Шаг 5: Последний fallback - никогда не возвращаем пустой список
        if len(all_results) == 0:
            fallback_results = self.fuzzy_fallback_search(query, top_k)
            for result in fallback_results:
                result['search_method'] = 'fuzzy_fallback'
            all_results.extend(fallback_results)
            search_strategy.append(f"fuzzy_fallback({len(fallback_results)})")
        
        # Убираем дубликаты по chunk_id
        seen_chunks = set()
        unique_results = []
        for result in all_results:
            if result['chunk_id'] not in seen_chunks:
                seen_chunks.add(result['chunk_id'])
                unique_results.append(result)
        
        # Sort by score, но сохраняем разнообразие источников
        unique_results.sort(key=lambda x: (x['score'], x.get('api_match', False)), reverse=True)
        
        # Ограничиваем до top_k
        final_results = unique_results[:top_k]
        
        # Шаг 6: Добавляем cross-links
        final_results = self.cross_linker.add_cross_links(final_results, query)
        
        # Шаг 7: Создаем умные preview и устанавливаем source_type если не установлен
        for result in final_results:
            result['preview'] = create_smart_preview(result['text'], query, 250)
            result['expand_available'] = True
            result['expand_hint'] = "💡 Use mcp_expand for full content"
            
            # Устанавливаем source_type если не установлен
            if not result.get('source_type'):
                if result.get('section') == 'plugin':
                    result['source_type'] = 'official_docs'
                elif result.get('section') == 'community_plugin':
                    result['source_type'] = 'community_code'
                elif result.get('api_match'):
                    result['source_type'] = 'api_reference'
                else:
                    # Fallback определение по URL
                    url = result.get('url', '')
                    if 'figma.com/plugin-docs' in url:
                        result['source_type'] = 'official_docs'
                    elif 'github.com' in url:
                        result['source_type'] = 'community_code'
                    else:
                        result['source_type'] = 'other'
        
        return {
            "query": query,
            "section": section,
            "top_k": top_k,
            "results": final_results,
            "search_strategy": search_strategy,
            "total_found": len(all_results),
            "api_symbols_detected": api_symbols
        }


if __name__ == "__main__":
    # Тестирование
    import asyncio
    import os
    
    async def test_search():
        db_path = os.getenv("DB_PATH", "data/meta.db")
        
        # Инициализация OpenAI клиента
        api_key = os.getenv("OPENAI_API_KEY")
        openai_client = openai.OpenAI(api_key=api_key) if api_key else None
        
        engine = UnifiedSearchEngine(db_path, openai_client)
        
        # Тест поиска
        result = await engine.unified_search("create rectangle", "auto", 3)
        
        print("=== Unified Search Test ===")
        print(f"Query: {result['query']}")
        print(f"Strategy: {result['search_strategy']}")
        print(f"Results: {len(result['results'])}")
        
        for i, r in enumerate(result['results'], 1):
            print(f"\n{i}. {r.get('title', 'Unknown')} (score: {r['score']:.3f})")
            print(f"   Method: {r.get('search_method', 'unknown')}")
            print(f"   Preview: {r.get('preview', '')[:100]}...")
            if r.get('cross_links'):
                print(f"   Cross-links: {r['cross_links']['type']}")
    
    asyncio.run(test_search())
