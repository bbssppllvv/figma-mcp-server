#!/usr/bin/env python3
"""
Query Normalizer - система нормализации пользовательских запросов
Преобразует живые пользовательские запросы в канонические термины для лучшего поиска
"""

import yaml
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class QueryNormalizer:
    """Нормализатор запросов с поддержкой синонимов и алиасов"""
    
    def __init__(self, aliases_file: str = "config/query_aliases.yaml"):
        self.aliases_file = Path(aliases_file)
        self.aliases: Dict[str, str] = {}
        self.load_aliases()
    
    def load_aliases(self):
        """Загружает словарь синонимов из YAML файла"""
        try:
            if not self.aliases_file.exists():
                logger.warning(f"Aliases file not found: {self.aliases_file}")
                return
                
            with open(self.aliases_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Объединяем все категории алиасов в один словарь
            for category, aliases in data.items():
                if isinstance(aliases, dict):
                    for alias, canonical in aliases.items():
                        # Нормализуем ключи для case-insensitive поиска
                        self.aliases[alias.lower().strip()] = canonical
            
            logger.info(f"Loaded {len(self.aliases)} query aliases")
            
        except Exception as e:
            logger.error(f"Failed to load aliases: {e}")
    
    def normalize_query(self, query: str) -> Tuple[str, List[str]]:
        """
        Нормализует запрос, возвращая канонический термин и дополнительные варианты
        
        Returns:
            Tuple[str, List[str]]: (normalized_query, additional_terms)
        """
        original_query = query.strip()
        normalized_query = original_query
        additional_terms = []
        
        # Case-insensitive поиск точного совпадения
        query_lower = original_query.lower()
        if query_lower in self.aliases:
            canonical = self.aliases[query_lower]
            normalized_query = canonical
            additional_terms.append(original_query)  # Сохраняем оригинал как дополнительный термин
            logger.info(f"Query normalized: '{original_query}' -> '{canonical}'")
        
        # Поиск частичных совпадений (если точного не найдено)
        elif not normalized_query or normalized_query == original_query:
            partial_matches = self._find_partial_matches(query_lower)
            if partial_matches:
                # Берем лучшее совпадение
                best_match = partial_matches[0]
                normalized_query = self.aliases[best_match]
                additional_terms.extend([original_query, best_match])
                logger.info(f"Query partially normalized: '{original_query}' -> '{normalized_query}' (via '{best_match}')")
        
        # Добавляем вариации термина
        additional_terms.extend(self._generate_variations(normalized_query))
        
        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_additional = []
        for term in additional_terms:
            if term not in seen and term != normalized_query:
                seen.add(term)
                unique_additional.append(term)
        
        return normalized_query, unique_additional
    
    def _find_partial_matches(self, query_lower: str) -> List[str]:
        """Находит частичные совпадения в алиасах"""
        matches = []
        
        for alias in self.aliases.keys():
            # Проверяем, содержится ли запрос в алиасе или наоборот
            if query_lower in alias or alias in query_lower:
                matches.append(alias)
        
        # Сортируем по релевантности (более короткие совпадения лучше)
        matches.sort(key=lambda x: abs(len(x) - len(query_lower)))
        return matches
    
    def _generate_variations(self, term: str) -> List[str]:
        """Генерирует вариации термина для более широкого поиска"""
        variations = []
        
        # Убираем префикс figma.
        if term.startswith("figma."):
            clean_term = term[6:]
            variations.append(clean_term)
            
            # Если есть точки, добавляем последнюю часть
            if "." in clean_term:
                method_name = clean_term.split(".")[-1]
                variations.append(method_name)
        
        # Добавляем camelCase вариации
        if "_" in term:
            camel_case = self._to_camel_case(term)
            variations.append(camel_case)
        
        # Добавляем snake_case вариации
        if re.search(r'[A-Z]', term):
            snake_case = self._to_snake_case(term)
            variations.append(snake_case)
        
        return variations
    
    def _to_camel_case(self, snake_str: str) -> str:
        """Преобразует snake_case в camelCase"""
        components = snake_str.split('_')
        return components[0] + ''.join(word.capitalize() for word in components[1:])
    
    def _to_snake_case(self, camel_str: str) -> str:
        """Преобразует camelCase в snake_case"""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def get_all_aliases(self) -> Dict[str, str]:
        """Возвращает все загруженные алиасы"""
        return self.aliases.copy()
    
    def add_alias(self, alias: str, canonical: str):
        """Добавляет новый алиас во время выполнения"""
        self.aliases[alias.lower().strip()] = canonical
        logger.info(f"Added runtime alias: '{alias}' -> '{canonical}'")
    
    def get_stats(self) -> Dict[str, int]:
        """Возвращает статистику нормализатора"""
        return {
            "total_aliases": len(self.aliases),
            "categories": len(set(alias.split()[0] for alias in self.aliases.keys() if " " in alias))
        }


def test_normalizer():
    """Тестирует нормализатор запросов"""
    normalizer = QueryNormalizer()
    
    test_queries = [
        "export PNG",
        "OAuth flow", 
        "variables mode",
        "selection change",
        "variant props",
        "post message",
        "figma.variables.setValueForMode",
        "create rectangle",
        "unknown query"
    ]
    
    print("🔍 Testing Query Normalizer:")
    print("=" * 50)
    
    for query in test_queries:
        normalized, additional = normalizer.normalize_query(query)
        print(f"'{query}' -> '{normalized}'")
        if additional:
            print(f"  Additional terms: {additional}")
        print()
    
    stats = normalizer.get_stats()
    print(f"📊 Stats: {stats['total_aliases']} aliases loaded")


if __name__ == "__main__":
    test_normalizer()
