#!/usr/bin/env python3
"""
Universal Expand Engine for MCP Figma Documentation
Universal content expansion with auto-detection and fallback
"""

import sqlite3
import logging
from typing import Dict, Any, Optional, List
import uuid

logger = logging.getLogger(__name__)


class ExpandEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_db_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def detect_id_type(self, id_string: str) -> str:
        """
        Automatically detects ID type
        
        Returns:
            'page' or 'chunk'
        """
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # First check if this exists in pages table
            cursor.execute("SELECT COUNT(*) FROM pages WHERE id = ?", (id_string,))
            page_count = cursor.fetchone()[0]
            
            if page_count > 0:
                conn.close()
                return 'page'
            
            # Then check in chunks table
            cursor.execute("SELECT COUNT(*) FROM chunks WHERE chunk_id = ?", (id_string,))
            chunk_count = cursor.fetchone()[0]
            
            conn.close()
            
            if chunk_count > 0:
                return 'chunk'
            else:
                # If not found in either table, try to guess by format
                # UUID is usually used for chunk_id
                try:
                    uuid.UUID(id_string)
                    return 'chunk'  # Assume chunk
                except ValueError:
                    return 'page'   # Assume page
        
        except Exception as e:
            logger.error(f"Error detecting ID type for {id_string}: {e}")
            return 'chunk'  # Fallback to chunk
    
    def expand_by_page_id(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Aggregates all chunks of a page"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get page information
            cursor.execute("""
                SELECT id, title, url, section, word_count, source
                FROM pages 
                WHERE id = ?
            """, (page_id,))
            
            page_row = cursor.fetchone()
            if not page_row:
                conn.close()
                return None
            
            # Get all page chunks, sorted by order
            cursor.execute("""
                SELECT chunk_id, chunk_index, text, n_tokens, chunk_of
                FROM chunks 
                WHERE page_id = ?
                ORDER BY chunk_index ASC
            """, (page_id,))
            
            chunks = cursor.fetchall()
            conn.close()
            
            if not chunks:
                return None
            
            # Combine all chunks into full text
            full_text = "\n\n".join([chunk['text'] for chunk in chunks])
            
            # Calculate statistics
            total_tokens = sum(chunk['n_tokens'] for chunk in chunks)
            word_count = len(full_text.split())
            
            return {
                "type": "page",
                "page_id": page_id,
                "title": page_row['title'],
                "url": page_row['url'],
                "section": page_row['section'],
                "source": page_row['source'] if 'source' in page_row.keys() else 'unknown',
                "word_count": word_count,
                "total_chunks": len(chunks),
                "total_tokens": total_tokens,
                "content": full_text,
                "chunks_info": [
                    {
                        "chunk_id": chunk['chunk_id'],
                        "chunk_index": chunk['chunk_index'],
                        "tokens": chunk['n_tokens'],
                        "preview": chunk['text'][:100] + "..." if len(chunk['text']) > 100 else chunk['text']
                    }
                    for chunk in chunks
                ],
                "navigation": {
                    "total_chunks": len(chunks),
                    "chunk_range": f"0-{len(chunks)-1}" if chunks else "0-0"
                }
            }
            
        except Exception as e:
            logger.error(f"Error expanding page {page_id}: {e}")
            return None
    
    def expand_by_chunk_id(self, chunk_id: str, context_window: int = 2) -> Optional[Dict[str, Any]]:
        """Returns chunk + context"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get chunk and page information
            cursor.execute("""
                SELECT c.chunk_id, c.page_id, c.chunk_index, c.chunk_of, c.text, c.n_tokens,
                       p.title, p.url, p.section, p.source
                FROM chunks c
                JOIN pages p ON p.id = c.page_id
                WHERE c.chunk_id = ?
            """, (chunk_id,))
            
            chunk_row = cursor.fetchone()
            if not chunk_row:
                conn.close()
                return None
            
            # Get neighboring chunks for context
            start_index = max(0, chunk_row['chunk_index'] - context_window)
            end_index = min(chunk_row['chunk_of'] - 1, chunk_row['chunk_index'] + context_window)
            
            cursor.execute("""
                SELECT chunk_id, chunk_index, text, n_tokens
                FROM chunks 
                WHERE page_id = ? AND chunk_index BETWEEN ? AND ?
                ORDER BY chunk_index ASC
            """, (chunk_row['page_id'], start_index, end_index))
            
            context_chunks_data = cursor.fetchall()
            conn.close()
            
            if not context_chunks_data:
                return None
            
            # Combine context chunks
            context_text = "\n\n".join([chunk['text'] for chunk in context_chunks_data])
            
            # Find target chunk position in context
            target_chunk_position = None
            for i, chunk in enumerate(context_chunks_data):
                if chunk['chunk_id'] == chunk_id:
                    target_chunk_position = i
                    break
            
            return {
                "type": "chunk",
                "chunk_id": chunk_id,
                "page_id": chunk_row['page_id'],
                "page_title": chunk_row['title'],
                "page_url": chunk_row['url'],
                "section": chunk_row['section'],
                "source": chunk_row['source'] if 'source' in chunk_row.keys() else 'unknown',
                "target_chunk_index": chunk_row['chunk_index'],
                "total_chunks_in_page": chunk_row['chunk_of'],
                "context_start_index": start_index,
                "context_end_index": end_index,
                "target_position_in_context": target_chunk_position,
                "expanded_content": context_text,
                "word_count": len(context_text.split()),
                "context_chunks": [
                    {
                        "chunk_id": chunk['chunk_id'],
                        "chunk_index": chunk['chunk_index'],
                        "tokens": chunk['n_tokens'],
                        "is_target": chunk['chunk_id'] == chunk_id,
                        "preview": chunk['text'][:100] + "..." if len(chunk['text']) > 100 else chunk['text']
                    }
                    for chunk in context_chunks_data
                ],
                "navigation": {
                    "position": f"chunk {chunk_row['chunk_index'] + 1} of {chunk_row['chunk_of']}",
                    "context_range": f"chunks {start_index} - {end_index}",
                    "has_prev": chunk_row['chunk_index'] > 0,
                    "has_next": chunk_row['chunk_index'] < chunk_row['chunk_of'] - 1
                }
            }
            
        except Exception as e:
            logger.error(f"Error expanding chunk {chunk_id}: {e}")
            return None
    
    def create_minimal_response(self, id_string: str, error_msg: str) -> Dict[str, Any]:
        """Creates minimal response for errors"""
        return {
            "type": "error",
            "id": id_string,
            "success": False,
            "error": error_msg,
            "fallback_attempted": True,
            "suggestion": "Try using the other expand type or check if the ID is correct"
        }
    
    def universal_expand(self, id_string: str, expand_type: str = "auto", 
                        context_window: int = 2) -> Dict[str, Any]:
        """
        Universal expansion with auto-detection and fallback
        
        Args:
            id_string: ID to expand
            expand_type: Expansion type ('auto', 'page', 'chunk')
            context_window: Context window size for chunk expansion
            
        Returns:
            Expansion result with guaranteed non-empty response
        """
        original_type = expand_type
        
        # Auto-detect ID type if not specified
        if expand_type == "auto":
            expand_type = self.detect_id_type(id_string)
            logger.info(f"Auto-detected ID type for {id_string}: {expand_type}")
        
        # First attempt
        try:
            if expand_type == "page":
                result = self.expand_by_page_id(id_string)
                if result:
                    return {
                        "success": True,
                        "data": result,
                        "method_used": "page_expansion",
                        "auto_detected": original_type == "auto"
                    }
            elif expand_type == "chunk":
                result = self.expand_by_chunk_id(id_string, context_window)
                if result:
                    return {
                        "success": True,
                        "data": result,
                        "method_used": "chunk_expansion",
                        "auto_detected": original_type == "auto"
                    }
        except Exception as e:
            logger.warning(f"First attempt failed for {id_string} as {expand_type}: {e}")
        
        # Fallback: try other type
        fallback_type = 'chunk' if expand_type == 'page' else 'page'
        logger.info(f"Trying fallback: {id_string} as {fallback_type}")
        
        try:
            if fallback_type == "page":
                result = self.expand_by_page_id(id_string)
                if result:
                    return {
                        "success": True,
                        "data": result,
                        "method_used": "page_expansion",
                        "fallback_used": True,
                        "original_type_attempted": expand_type,
                        "auto_detected": original_type == "auto"
                    }
            elif fallback_type == "chunk":
                result = self.expand_by_chunk_id(id_string, context_window)
                if result:
                    return {
                        "success": True,
                        "data": result,
                        "method_used": "chunk_expansion", 
                        "fallback_used": True,
                        "original_type_attempted": expand_type,
                        "auto_detected": original_type == "auto"
                    }
        except Exception as e:
            logger.warning(f"Fallback attempt failed for {id_string} as {fallback_type}: {e}")
        
        # Last fallback: try to find anything in DB
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Search by partial match in chunk_id
            cursor.execute("""
                SELECT c.chunk_id, c.text, p.title, p.url
                FROM chunks c
                JOIN pages p ON p.id = c.page_id
                WHERE c.chunk_id LIKE '%' || ? || '%'
                LIMIT 1
            """, (id_string[:8],))  # Use first 8 characters
            
            row = cursor.fetchone()
            if row:
                conn.close()
                return {
                    "success": True,
                    "data": {
                        "type": "partial_match",
                        "chunk_id": row['chunk_id'],
                        "content": row['text'],
                        "page_title": row['title'],
                        "page_url": row['url'],
                        "warning": f"Exact ID not found. Showing partial match for {id_string}"
                    },
                    "method_used": "partial_match_fallback",
                    "fallback_used": True
                }
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Even partial match failed for {id_string}: {e}")
        
        # Absolute fallback - return informative error
        return {
            "success": False,
            "error": f"Could not expand ID: {id_string}",
            "attempted_methods": [expand_type, fallback_type, "partial_match"],
            "suggestion": "Check if the ID is correct or try searching for the content instead",
            "id": id_string,
            "auto_detected": original_type == "auto"
        }
    
    def get_navigation_info(self, page_id: str, chunk_id: Optional[str] = None) -> Dict[str, Any]:
        """Gets navigation information for page or chunk"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            if chunk_id:
                # Navigation for specific chunk
                cursor.execute("""
                    SELECT chunk_index, chunk_of
                    FROM chunks
                    WHERE chunk_id = ? AND page_id = ?
                """, (chunk_id, page_id))
                
                chunk_info = cursor.fetchone()
                if chunk_info:
                    return {
                        "current_chunk": chunk_info['chunk_index'],
                        "total_chunks": chunk_info['chunk_of'],
                        "has_prev": chunk_info['chunk_index'] > 0,
                        "has_next": chunk_info['chunk_index'] < chunk_info['chunk_of'] - 1,
                        "position": f"{chunk_info['chunk_index'] + 1} of {chunk_info['chunk_of']}"
                    }
            else:
                # Navigation for page
                cursor.execute("""
                    SELECT COUNT(*) as total_chunks
                    FROM chunks
                    WHERE page_id = ?
                """, (page_id,))
                
                count_info = cursor.fetchone()
                if count_info:
                    return {
                        "total_chunks": count_info['total_chunks'],
                        "type": "page_overview"
                    }
            
            conn.close()
            return {}
            
        except Exception as e:
            logger.error(f"Error getting navigation info: {e}")
            return {}


if __name__ == "__main__":
    # Testing
    import os
    
    db_path = os.getenv("DB_PATH", "data/meta.db")
    engine = ExpandEngine(db_path)
    
    # Test auto-detection of type
    test_ids = [
        "3bd7f1c3-1f0e-5610-913e-1cff6f6f648c",  # page_id from audit
        "db2a544c-03c3-5557-83e1-8b13ed625a3f",  # chunk_id from audit
    ]
    
    for test_id in test_ids:
        detected_type = engine.detect_id_type(test_id)
        print(f"ID: {test_id[:20]}... -> Type: {detected_type}")
        
        # Test universal expand
        result = engine.universal_expand(test_id, "auto")
        print(f"Expand result: success={result['success']}, method={result.get('method_used', 'none')}")
        if result['success']:
            data = result['data']
            print(f"Content length: {len(data.get('content', data.get('expanded_content', '')))}")
        print("---")
