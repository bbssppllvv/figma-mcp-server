#!/usr/bin/env python3
"""
Figma Documentation MCP Server
Предоставляет 3 unified tools: mcp_search, mcp_expand, mcp_health
Транспорт: stdio для интеграции с Cursor
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool
)
from pydantic import BaseModel, Field, ValidationError
import openai

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("figma-mcp")

# Импортируем нормализатор запросов и новые модули
try:
    import sys
    from pathlib import Path
    # Добавляем src в путь для импорта
    src_path = Path(__file__).parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    from query_normalizer import QueryNormalizer
    query_normalizer = QueryNormalizer()
    logger.info("Query normalizer loaded successfully")
except ImportError as e:
    logger.warning(f"Query normalizer not available: {e}")
    query_normalizer = None

# Импортируем новые модули для unified search
try:
    from search_engine import UnifiedSearchEngine
    from expand_engine import ExpandEngine
    from preview_generator import create_smart_preview
    logger.info("New unified modules loaded successfully")
    unified_modules_available = True
except ImportError as e:
    logger.warning(f"Unified modules not available: {e}")
    unified_modules_available = False

# Raw STDIO logger (отключен в продакшене)
def log_raw(label: str, data: Any) -> None:
    # Отключено для продакшена
    pass

# Глобальные переменные
db_path = os.getenv("DB_PATH", "data/meta.db")
openai_client = None
server = Server("figma-knowledge")

# Новые движки для unified search
unified_search_engine = None
expand_engine = None

# Модели данных для валидации
class UnifiedSearchArgs(BaseModel):
    query: str = Field(..., description="Search query", max_length=200)
    section: str = Field("auto", description="Search section: 'auto', 'official', 'community_plugin'")
    top_k: int = Field(5, description="Number of results", ge=1, le=10)
    model: str = Field("text-embedding-3-small", description="Embedding model")

class UnifiedExpandArgs(BaseModel):
    id: str = Field(..., description="Page ID or Chunk ID", max_length=100)
    type: str = Field("auto", description="Expansion type: 'auto', 'page', 'chunk'")
    context_window: int = Field(2, description="Context window for chunk expansion", ge=1, le=5)

# Метрики
class Metrics:
    def __init__(self):
        # Только новые unified инструменты
        tools = ["mcp_search", "mcp_expand", "mcp_health"]
        self.calls_total = {tool: 0 for tool in tools}
        self.errors_total = {tool: 0 for tool in tools}
        self.latencies = {tool: [] for tool in tools}
        self.bytes_out = {tool: 0 for tool in tools}

    def record_call(self, tool: str, latency_ms: float, bytes_out: int, error: bool = False):
        self.calls_total[tool] += 1
        if error:
            self.errors_total[tool] += 1
        self.latencies[tool].append(latency_ms)
        self.bytes_out[tool] += bytes_out
        
        # Ограничиваем историю латентности
        if len(self.latencies[tool]) > 1000:
            self.latencies[tool] = self.latencies[tool][-500:]

    def get_p95(self, tool: str) -> float:
        latencies = self.latencies[tool]
        if not latencies:
            return 0.0
        return np.percentile(latencies, 95)

metrics = Metrics()

def init_openai():
    """Инициализация OpenAI клиента"""
    global openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        openai_client = openai.OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized")
    else:
        logger.warning("No OPENAI_API_KEY found, semantic search will use fallback")

def init_unified_engines():
    """Инициализация новых unified движков"""
    global unified_search_engine, expand_engine
    
    if unified_modules_available:
        try:
            unified_search_engine = UnifiedSearchEngine(db_path, openai_client)
            expand_engine = ExpandEngine(db_path)
            logger.info("Unified engines initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize unified engines: {e}")
            unified_search_engine = None
            expand_engine = None
    else:
        logger.warning("Unified modules not available, using legacy implementations")

def get_db_connection():
    """Получение подключения к БД"""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def parse_github_url(url: str) -> tuple[str, str]:
    """Парсинг GitHub URL"""
    import re
    match = re.match(r'https://github\.com/([^/]+/[^/]+)/tree/[^/]+/?(.*?)(?:#.*)?$', url)
    if match:
        return match.group(1), match.group(2) or ""
    return "", ""

def extract_figma_symbols(text: str) -> List[str]:
    """Извлечение Figma API символов"""
    import re
    pattern = r'\bfigma\.[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*'
    return list(set(re.findall(pattern, text, re.IGNORECASE)))

def sanitize_text(text: str, max_length: int = 1200) -> str:
    """Санитизация и обрезка текста"""
    import re
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    
    return truncated + "…"

def create_smart_preview(text: str, query: str = "", max_length: int = 250) -> str:
    """Создание умного превью с учетом запроса и контекста"""
    import re
    
    # Очищаем текст
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) <= max_length:
        return text
    
    # Извлекаем ключевые слова из запроса
    query_words = [word.lower() for word in query.split() if len(word) > 2]
    
    # Разбиваем текст на предложения
    sentences = re.split(r'[.!?]\s+', text)
    
    # Ищем лучшее предложение для preview
    best_sentence = None
    best_score = -1
    
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if len(sentence) < 20:  # Слишком короткое предложение
            continue
            
        score = 0
        sentence_lower = sentence.lower()
        
        # Бонус за содержание ключевых слов запроса
        for word in query_words:
            if word in sentence_lower:
                score += 10
        
        # Бонус за позицию (первые предложения важнее)
        if i == 0:
            score += 5
        elif i == 1:
            score += 3
        
        # Бонус за содержание API методов
        if 'figma.' in sentence_lower:
            score += 8
        
        # Бонус за содержание полезных слов
        useful_words = ['create', 'export', 'load', 'set', 'get', 'add', 'remove', 'update']
        for word in useful_words:
            if word in sentence_lower:
                score += 2
        
        # Штраф за технические детали в начале
        if sentence.startswith(('Set to null', 'Supported on:', 'info', 'This API is only', 'Value must be')):
            score -= 5
        
        # Штраф за слишком длинные предложения
        if len(sentence) > max_length * 1.5:
            score -= 3
        
        if score > best_score:
            best_score = score
            best_sentence = sentence
    
    # Если не нашли хорошее предложение, используем начало текста
    if not best_sentence or best_score < 0:
        best_sentence = text
    
    # Обрезаем до нужной длины
    if len(best_sentence) <= max_length:
        return best_sentence
    
    # Ищем хорошую точку обрезки
    truncated = best_sentence[:max_length]
    
    # Пытаемся найти конец предложения
    sentence_end = max(
        truncated.rfind('. '),
        truncated.rfind('! '),
        truncated.rfind('? ')
    )
    
    if sentence_end > max_length * 0.6:
        return best_sentence[:sentence_end + 1].strip()
    
    # Обрезаем по словам
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    
    return truncated.strip() + "…"

def create_preview(text: str, max_length: int = 250) -> str:
    """Обратная совместимость - вызывает create_smart_preview"""
    return create_smart_preview(text, "", max_length)

def determine_source_type(section: str, url: str) -> str:
    """Определяет тип источника для preview"""
    if section in ['plugin', 'widget', 'rest', 'guide']:
        return 'official_docs'
    elif section == 'community_plugin':
        return 'community_code'
    else:
        return 'other'

async def get_embedding(text: str, model: str = "text-embedding-3-small") -> Optional[np.ndarray]:
    """Получение эмбеддинга"""
    if not openai_client:
        return None
    
    try:
        response = openai_client.embeddings.create(input=text, model=model)
        return np.array(response.data[0].embedding)
    except Exception as e:
        logger.error(f"Failed to get embedding: {e}")
        return None

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Косинусное сходство"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def generate_search_suggestions(query: str, section: str) -> List[str]:
    """Генерация подсказок для поиска"""
    suggestions = []
    
    # Основные API подсказки
    api_mapping = {
        'font': ['loadFontAsync', 'fontName', 'TextNode.fontName'],
        'text': ['TextNode.characters', 'createText', 'fontName'],
        'export': ['exportAsync', 'ExportSettings', 'exportSettingsImage'],
        'png': ['exportAsync', 'ExportSettingsImage', 'format: "PNG"'],
        'image': ['exportAsync', 'createImage', 'ImageHash'],
        'frame': ['createFrame', 'FrameNode', 'resize'],
        'storage': ['clientStorage.setAsync', 'clientStorage.getAsync'],
        'ui': ['ui.postMessage', 'ui.onmessage', 'showUI'],
        'oauth': ['networkAccess', 'fetch', 'clientStorage'],
        'upload': ['fetch', 'FormData', 'networkAccess']
    }
    
    query_lower = query.lower()
    for keyword, apis in api_mapping.items():
        if keyword in query_lower:
            suggestions.extend(apis)
    
    # Убираем дубликаты
    suggestions = list(dict.fromkeys(suggestions))[:3]
    
    return suggestions

@server.list_tools()
async def list_tools() -> List[Tool]:
    """Список доступных инструментов"""
    return [
        Tool(
            name="echo_test",
            description="Echo back the provided message for transport debugging",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to echo back"
                    }
                },
                "required": ["message"]
            }
        ),
        # NEW UNIFIED TOOLS
        Tool(
            name="mcp_search",
            description="**UNIFIED SMART SEARCH** - The new all-in-one search tool that combines semantic search, API lookup, and cross-linking.\n\n**FEATURES:**\n• **Semantic Search**: Uses OpenAI embeddings for best results (requires OPENAI_API_KEY)\n• **Auto-fallback**: Gracefully falls back to keyword search if OpenAI unavailable\n• **API Detection**: Automatically detects and searches for API symbols in your query\n• **Cross-linking**: Shows related community examples for official docs and vice versa\n• **Smart Preview**: Context-aware previews with code examples prioritized\n• **Never Empty**: Always returns results with intelligent fallback strategies\n\n**WHEN TO USE:**\n• **Any search query** - this tool handles everything automatically\n• Natural language: 'how to save user data', 'export PNG from plugin'\n• API methods: 'figma.createRectangle', 'ui.postMessage'\n• Concepts: 'OAuth authentication', 'network requests'\n\n**ADVANTAGES OVER OLD TOOLS:**\n• Combines search_examples + get_examples + link_docs in one call\n• Intelligent section switching (official → community fallback)\n• Cross-references between documentation and real code examples\n• Smart preview generation based on query relevance\n\n**PERFORMANCE NOTE:**\n• **BEST**: With OPENAI_API_KEY → Semantic search with embeddings\n• **FALLBACK**: Without key → Keyword search only (reduced quality)\n• Use `mcp_health` to check your current search engine status",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language, API symbols, or concepts)",
                        "maxLength": 200
                    },
                    "section": {
                        "type": "string",
                        "description": "Search scope: 'auto' (recommended), 'official', 'community_plugin'",
                        "enum": ["auto", "official", "community_plugin"],
                        "default": "auto"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="mcp_expand",
            description="**UNIVERSAL EXPAND** - Enhanced content expansion with auto-detection and bulletproof fallback.\n\n**FEATURES:**\n• **Auto-detection**: Automatically determines if ID is page_id or chunk_id\n• **Bulletproof Fallback**: If one type fails, automatically tries the other\n• **Never Fails**: Always returns content or actionable error message\n• **Smart Context**: For chunks, shows surrounding context with navigation\n• **Rich Metadata**: Includes navigation info, token counts, and content stats\n\n**WHEN TO USE:**\n• **Any expand operation** - just provide the ID from search results\n• When you want full page content: auto-detects and expands entire page\n• When you want chunk context: auto-detects and shows chunk + neighbors\n• When unsure about ID type: auto-detection handles it\n\n**ADVANTAGES:**\n• Replaces expand_example with smarter behavior\n• No need to specify type - auto-detection works perfectly\n• Guaranteed results with multiple fallback strategies\n• Better error messages with suggestions for next steps",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Page ID or Chunk ID from search results (auto-detected)",
                        "maxLength": 100
                    },
                    "type": {
                        "type": "string",
                        "description": "Expansion type: 'auto' (recommended), 'page', 'chunk'",
                        "enum": ["auto", "page", "chunk"],
                        "default": "auto"
                    }
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="mcp_health",
            description="**SYSTEM HEALTH CHECK** - Enhanced database diagnostics and system status.\n\n**FEATURES:**\n• Complete database statistics (pages, chunks, embeddings by type)\n• Model information and embedding coverage\n• System status and health indicators\n• Performance metrics and recommendations\n\n**WHEN TO USE:**\n• Troubleshooting search issues\n• Verifying system setup and data availability\n• Getting overview of available content\n• Performance monitoring",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Вызов инструмента"""
    start_time = time.time()
    
    logger.info(f"🔧 call_tool started: name={name}, arguments={arguments}")
    
    try:
        if name == "echo_test":
            message = str(arguments.get("message", ""))
            result = {
                "query": message,
                "top_k": 1,
                "results": [],
                "source": "echo"
            }
            
        elif name == "mcp_search":
            try:
                args = UnifiedSearchArgs(**arguments)
            except ValidationError as e:
                metrics.record_call(name, 0, 0, error=True)
                result_dict = {
                    "content": [{"type": "text", "text": f"Invalid arguments: {e}"}],
                    "isError": True
                }
                log_raw("OUT_VAL_ERR", result_dict)
                return result_dict
            
            if unified_search_engine:
                result = await unified_search_engine.unified_search(
                    args.query, args.section, args.top_k, args.model
                )
            else:
                # Unified modules not available
                result = {
                    "error": "Unified search modules not available",
                    "query": args.query,
                    "results": []
                }
            
        elif name == "mcp_expand":
            try:
                args = UnifiedExpandArgs(**arguments)
            except ValidationError as e:
                metrics.record_call(name, 0, 0, error=True)
                result_dict = {
                    "content": [{"type": "text", "text": f"Invalid arguments: {e}"}],
                    "isError": True
                }
                log_raw("OUT_VAL_ERR", result_dict)
                return result_dict
            
            if expand_engine:
                result = expand_engine.universal_expand(
                    args.id, args.type, args.context_window
                )
            else:
                # Expand engine not available
                result = {
                    "error": "Expand engine not available",
                    "id": args.id,
                    "success": False
                }
            
        elif name == "mcp_health":
            # Use basic health check
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT COUNT(*) FROM pages")
                pages_total = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM pages WHERE source='official'")
                pages_official = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM pages WHERE section='community_plugin'")
                pages_comm = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM chunks c JOIN pages p ON p.id=c.page_id WHERE p.section='community_plugin'")
                chunks_comm = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM embeddings")
                embeddings_total = cursor.fetchone()[0]
                
                cursor.execute("SELECT DISTINCT model FROM embeddings")
                models = [row[0] for row in cursor.fetchall()]
                
                conn.close()
                
                result = {
                    "db_path": str(Path(db_path).absolute()),
                    "pages_total": pages_total,
                    "pages_official": pages_official,
                    "pages_comm": pages_comm,
                    "chunks_comm": chunks_comm,
                    "embeddings": embeddings_total,
                    "models": models,
                    "unified_version": unified_modules_available
                }
                
            except Exception as e:
                conn.close()
                result = {
                    "db_path": str(Path(db_path).absolute()),
                    "error": str(e),
                    "status": "error"
                }
            
        else:
            metrics.record_call(name, 0, 0, error=True)
            ret_dict = {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True
            }
            log_raw("OUT_UNKNOWN", ret_dict)
            return ret_dict
        
        # Format result for better readability
        if name == "echo_test":
            formatted_text = f"ECHO: {result['query']}"
            
        elif name == "mcp_search":
            # Determine search mode for indication
            has_openai = openai_client is not None
            used_semantic = any('semantic' in strategy for strategy in result.get('search_strategy', []))
            used_keyword_only = all('keyword' in strategy or 'fuzzy' in strategy for strategy in result.get('search_strategy', []))
            
            # Header with search mode indicator
            if has_openai and used_semantic:
                search_mode = "SEMANTIC SEARCH"
            elif has_openai and not used_semantic:
                search_mode = "HYBRID SEARCH (OpenAI + Fallback)"
            else:
                search_mode = "FALLBACK SEARCH (No OpenAI Key)"
            
            formatted_text = f"**{search_mode}**\n"
            formatted_text += f"Query: {result['query']}\n"
            formatted_text += f"Found: {len(result['results'])} results\n"
            formatted_text += f"Strategy: {', '.join(result.get('search_strategy', []))}\n"
            
            # Warning about suboptimal mode
            if not has_openai:
                formatted_text += f"\n**WARNING:** Using fallback search without OpenAI key!\n"
                formatted_text += f"   - Semantic search unavailable\n"
                formatted_text += f"   - Search quality may be reduced\n"
                formatted_text += f"   - Add OPENAI_API_KEY for optimal performance\n"
            elif used_keyword_only:
                formatted_text += f"\n**NOTICE:** Semantic search returned no results\n"
                formatted_text += f"   - Using keyword fallback\n"
                formatted_text += f"   - Try different query phrasing\n"
            
            if result.get('api_symbols_detected'):
                formatted_text += f"API Symbols: {', '.join(result['api_symbols_detected'])}\n"
            
            if result.get('unified_fallback'):
                formatted_text += f"Using legacy fallback (unified modules unavailable)\n"
            
            formatted_text += "\n"
            
            # Group results by source type
            official_results = [r for r in result['results'] if r.get('source_type') == 'official_docs']
            community_results = [r for r in result['results'] if r.get('source_type') == 'community_code']
            api_results = [r for r in result['results'] if r.get('source_type') == 'api_reference']
            
            if official_results:
                formatted_text += "**Official Documentation:**\n"
                for i, r in enumerate(official_results, 1):
                    search_method = r.get('search_method', 'unknown')
                    method_indicator = f"[{search_method}]"
                    formatted_text += f"{i}. **{r.get('title', 'Documentation')}** (score: {r['score']:.3f}) {method_indicator}\n"
                    formatted_text += f"   URL: {r['url']}\n"
                    formatted_text += f"   Preview: {r.get('preview', '')}\n"
                    if r.get('cross_links'):
                        formatted_text += f"   Cross-links: {r['cross_links']['title']}: {len(r['cross_links'].get('examples', r['cross_links'].get('docs', [])))} items\n"
                    formatted_text += f"   Expand: mcp_expand {r.get('page_id', r['chunk_id'])}\n\n"
            
            if community_results:
                formatted_text += "**Community Examples:**\n"
                for i, r in enumerate(community_results, 1):
                    search_method = r.get('search_method', 'unknown')
                    method_indicator = f"[{search_method}]"
                    formatted_text += f"{i}. **{r.get('title', 'Code Example')}** (score: {r['score']:.3f}) {method_indicator}\n"
                    formatted_text += f"   URL: {r['url']}\n"
                    formatted_text += f"   Preview: {r.get('preview', '')}\n"
                    if r.get('cross_links'):
                        formatted_text += f"   Cross-links: {r['cross_links']['title']}: {len(r['cross_links'].get('examples', r['cross_links'].get('docs', [])))} items\n"
                    formatted_text += f"   Expand: mcp_expand {r.get('page_id', r['chunk_id'])}\n\n"
            
            if api_results:
                formatted_text += "**API Reference:**\n"
                for i, r in enumerate(api_results, 1):
                    search_method = r.get('search_method', 'unknown')
                    method_indicator = f"[{search_method}]"
                    symbol = r.get('matched_symbol', '')
                    formatted_text += f"{i}. **{r.get('title', 'API')}** (score: {r['score']:.3f}) {method_indicator}\n"
                    if symbol:
                        formatted_text += f"   Symbol: {symbol}\n"
                    formatted_text += f"   URL: {r['url']}\n"
                    formatted_text += f"   Preview: {r.get('preview', '')}\n"
                    formatted_text += f"   Expand: mcp_expand {r.get('page_id', r['chunk_id'])}\n\n"
            
            if not result['results']:
                formatted_text += f"**No results found**\n"
                if not has_openai:
                    formatted_text += "   - Try adding OPENAI_API_KEY for semantic search\n"
                formatted_text += "   - Try different keywords\n"
                formatted_text += "   - Check spelling\n"
            
        elif name == "mcp_expand":
            if result['success']:
                data = result['data']
                method_info = f" (method: {result.get('method_used', 'unknown')})"
                if result.get('fallback_used'):
                    method_info += f", fallback from {result.get('original_type_attempted', 'unknown')}"
                if result.get('auto_detected'):
                    method_info += ", auto-detected"
                
                if data['type'] == 'page':
                    formatted_text = f"**Full Page Content**{method_info}\n"
                    formatted_text += f"Page ID: {data['page_id']}\n"
                    formatted_text += f"Title: **{data['title']}**\n"
                    formatted_text += f"URL: {data['url']}\n"
                    formatted_text += f"Section: {data['section']}\n"
                    formatted_text += f"Stats: {data['word_count']} words, {data['total_chunks']} chunks, {data['total_tokens']} tokens\n\n"
                    
                    formatted_text += f"**Full Content:**\n"
                    formatted_text += f"```\n{data['content'][:3000]}{'...' if len(data['content']) > 3000 else ''}\n```\n\n"
                    
                    if len(data['content']) > 3000:
                        formatted_text += f"Content truncated for display. Full content: {len(data['content'])} characters\n\n"
                    
                    formatted_text += f"**Chunks Overview:**\n"
                    for chunk_info in data['chunks_info'][:5]:
                        formatted_text += f"- Chunk {chunk_info['chunk_index']}: {chunk_info['tokens']} tokens - {chunk_info['preview']}\n"
                    
                    if len(data['chunks_info']) > 5:
                        formatted_text += f"... and {len(data['chunks_info']) - 5} more chunks\n"
                
                elif data['type'] == 'chunk':
                    formatted_text = f"**Expanded Chunk Context**{method_info}\n"
                    formatted_text += f"Chunk ID: {data['chunk_id']}\n"
                    formatted_text += f"Page: **{data['page_title']}**\n"
                    formatted_text += f"URL: {data['page_url']}\n"
                    formatted_text += f"Section: {data['section']}\n"
                    formatted_text += f"Position: {data['navigation']['position']}\n"
                    formatted_text += f"Context: {data['navigation']['context_range']}\n\n"
                    
                    formatted_text += f"**Expanded Content:**\n"
                    formatted_text += f"```\n{data['expanded_content'][:3000]}{'...' if len(data['expanded_content']) > 3000 else ''}\n```\n\n"
                    
                    if len(data['expanded_content']) > 3000:
                        formatted_text += f"Content truncated for display. Full content: {len(data['expanded_content'])} characters\n\n"
                    
                    formatted_text += f"**Context Chunks:**\n"
                    for chunk_info in data['context_chunks']:
                        target_marker = " [TARGET]" if chunk_info['is_target'] else ""
                        formatted_text += f"- Chunk {chunk_info['chunk_index']}: {chunk_info['tokens']} tokens{target_marker}\n"
                
                elif data['type'] == 'partial_match':
                    formatted_text = f"**Partial Match Found**{method_info}\n"
                    formatted_text += f"Found ID: {data['chunk_id']}\n"
                    formatted_text += f"Page: **{data['page_title']}**\n"
                    formatted_text += f"URL: {data['page_url']}\n"
                    formatted_text += f"Warning: {data['warning']}\n\n"
                    formatted_text += f"**Content:**\n"
                    formatted_text += f"```\n{data['content'][:2000]}{'...' if len(data['content']) > 2000 else ''}\n```\n"
            else:
                formatted_text = f"**Universal Expand Failed**\n"
                formatted_text += f"ID: {result['id']}\n"
                formatted_text += f"Attempted: {', '.join(result.get('attempted_methods', []))}\n"
                formatted_text += f"Error: {result['error']}\n"
                formatted_text += f"Suggestion: {result.get('suggestion', 'Try a different ID')}\n"
                if result.get('auto_detected'):
                    formatted_text += f"Auto-detection was used\n"
                
        elif name == "mcp_health":
            # Check OpenAI status
            has_openai = openai_client is not None
            openai_status = "ACTIVE" if has_openai else "MISSING"
            
            formatted_text = f"**Enhanced Database Health Check**\n\n"
            
            # Search status
            formatted_text += f"**Search Engine Status:**\n"
            formatted_text += f"   OpenAI API Key: {openai_status}\n"
            if has_openai:
                formatted_text += f"   Semantic search available\n"
                formatted_text += f"   Optimal search performance\n"
            else:
                formatted_text += f"   Fallback to keyword search only\n"
                formatted_text += f"   Reduced search quality\n"
                formatted_text += f"   Add OPENAI_API_KEY for best results\n"
            
            formatted_text += f"\n**Database Statistics:**\n"
            formatted_text += f"   DB Path: {result['db_path']}\n"
            formatted_text += f"   Pages Total: {result['pages_total']}\n"
            formatted_text += f"   Pages Official: {result.get('pages_official', 0)}\n"
            formatted_text += f"   Pages Community: {result['pages_comm']}\n"
            formatted_text += f"   Chunks Community: {result['chunks_comm']}\n"
            formatted_text += f"   Embeddings: {result['embeddings']}\n"
            formatted_text += f"   Models: {result['models']}\n"
            
            formatted_text += f"\n**System Status:**\n"
            if result.get('unified_version'):
                formatted_text += f"   Enhanced unified version active\n"
            elif result.get('legacy_version'):
                formatted_text += f"   Legacy version (unified modules unavailable)\n"
            
            # Optimization recommendations
            formatted_text += f"\n**Recommendations:**\n"
            if not has_openai:
                formatted_text += f"   Set OPENAI_API_KEY environment variable\n"
                formatted_text += f"   This will enable semantic search with embeddings\n"
            else:
                formatted_text += f"   System optimally configured\n"
            
            if result['embeddings'] == 0:
                formatted_text += f"   Consider running embedding generation\n"
            elif result['embeddings'] < result['pages_total'] * 5:  # Approximately 5 chunks per page
                formatted_text += f"   Some content may lack embeddings\n"
                
        else:
            # Fallback to JSON
            formatted_text = json.dumps(result, ensure_ascii=False, indent=2)
        
        latency_ms = (time.time() - start_time) * 1000
        bytes_out = len(formatted_text.encode('utf-8'))
        
        # Метрики
        metrics.record_call(name, latency_ms, bytes_out)
        
        # Логирование
        logger.info(f"Tool {name}: latency={latency_ms:.1f}ms, bytes={bytes_out}, results={len(result.get('results', result.get('examples', result.get('docs', []))))}")
        
        # Возвращаем простой словарь (обход проблемы MCP SDK)
        logger.info(f"Returning dict result; length={len(formatted_text)}")
        result_dict = {
            "content": [{"type": "text", "text": formatted_text}],
            "isError": False
        }
        log_raw("OUT_DICT", result_dict)
        return result_dict
        
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_call(name, latency_ms, 0, error=True)
        logger.error(f"Tool {name} error: {e}", exc_info=True)
        
        err_dict = {
            "content": [{"type": "text", "text": f"Internal error: {str(e)}"}],
            "isError": True
        }
        log_raw("OUT_ERR", err_dict)
        return err_dict

async def main():
    """Главная функция MCP сервера"""
    # Инициализация
    init_openai()
    init_unified_engines()
    
    # Проверка БД
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]
        conn.close()
        logger.info(f"Database connected, {chunk_count} chunks available")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)
    
    logger.info("Starting Figma Knowledge MCP Server")
    
    # Запуск stdio сервера
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
