"""Загрузка и парсинг YAML-конфигурации (DSL) для краулера."""

from dataclasses import dataclass, field
from typing import List, Dict
import yaml


@dataclass
class ExtractRule:
    """Правило извлечения данных для конкретного блока."""
    name: str = ""
    selector: str = ""
    fields: Dict[str, str] = field(default_factory=dict)
    profile_link: str = ""


@dataclass
class Navigation:
    """Параметры навигации (пагинация)."""
    follow_links: str = ""
    max_depth: int = 0


@dataclass
class Filters:
    """Правила фильтрации и пост-обработки."""
    must_contain: List[str] = field(default_factory=list)
    exclude_empty: List[str] = field(default_factory=list)


@dataclass
class CrawlerTask:
    """Основные параметры задачи сбора."""
    name: str = ""
    start_urls: List[str] = field(default_factory=list)
    extract_rules: List[ExtractRule] = field(default_factory=list)
    navigation: Navigation = field(default_factory=Navigation)
    filters: Filters = field(default_factory=Filters)


@dataclass
class Config:
    """Корневая структура DSL-файла."""
    task: CrawlerTask = field(default_factory=CrawlerTask)


def load_config(filename: str) -> Config:
    """Читает YAML-файл по указанному пути и десериализует его в структуру Config."""
    with open(filename, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    task_data = data.get("crawler_task", {})

    extract_rules = []
    for rule in task_data.get("extract_rules", []):
        extract_rules.append(ExtractRule(
            name=rule.get("name", ""),
            selector=rule.get("selector", ""),
            fields=rule.get("fields", {}),
            profile_link=rule.get("profile_link", ""),
        ))

    navigation = Navigation(
        follow_links=task_data.get("navigation", {}).get("follow_links", ""),
        max_depth=task_data.get("navigation", {}).get("max_depth", 0),
    )

    filters = Filters(
        must_contain=task_data.get("filters", {}).get("must_contain", []),
        exclude_empty=task_data.get("filters", {}).get("exclude_empty", []),
    )

    task = CrawlerTask(
        name=task_data.get("name", ""),
        start_urls=task_data.get("start_urls", []),
        extract_rules=extract_rules,
        navigation=navigation,
        filters=filters,
    )

    return Config(task=task)
