"""Асинхронные воркеры на aiohttp для параллельной обработки URL."""

import asyncio
import logging
from typing import List, Dict
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from internal.config.dsl import Config, ExtractRule, Filters
from internal.parser import html as parser

logger = logging.getLogger("worker")

# User-Agent для запросов
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Таймаут для HTTP-запросов
TIMEOUT = aiohttp.ClientTimeout(total=15)


class Result:
    """Структура извлеченных данных."""

    def __init__(self, url: str, extracted: List[Dict[str, str]] = None, error: Exception = None):
        self.url = url
        self.extracted = extracted or []
        self.error = error


async def fetch(session: aiohttp.ClientSession, url: str) -> str:
    """Выполняет HTTP-GET запрос и возвращает текст ответа."""
    async with session.get(url, headers=DEFAULT_HEADERS) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP status: {response.status}")
        return await response.text()


async def process_url(
    session: aiohttp.ClientSession,
    url_str: str,
    rule: ExtractRule,
    filters: Filters,
    allow_deep: bool = True,
) -> Result:
    """Выполняет загрузку, парсинг и deep crawl для одного URL."""
    result = Result(url=url_str)
    logger.info("Начало обработки: %s (deep=%s)", url_str, allow_deep)

    try:
        html = await fetch(session, url_str)
    except Exception as e:
        result.error = e
        logger.error("Ошибка HTTP: %s", e)
        return result

    logger.info("Получено байт: %d", len(html.encode("utf-8")))

    soup = BeautifulSoup(html, "lxml")

    # CSS-парсинг
    extracted = parser.parse_page(soup, rule)
    logger.info("CSS ParsePage нашел записей: %d", len(extracted))

    # Fallback: парсинг HTML-таблиц (структура kubsu.ru и аналогичных)
    if not extracted:
        extracted = parser.parse_tables(soup)
        logger.info("Парсинг таблиц нашел записей: %d", len(extracted))

    # Deep crawl по профилям (если нашлись карточки или таблицы — и их не слишком много)
    if allow_deep and rule.profile_link and 0 < len(extracted) <= 20:
        profile_links = parser.extract_profile_links(soup, rule)
        logger.info("Найдено ссылок на профили: %d", len(profile_links))

        max_profiles = 5
        for i, link in enumerate(profile_links[:max_profiles]):
            profile_url = urljoin(url_str, link)
            logger.info("Обход профиля %d: %s", i + 1, profile_url)

            profile_res = await process_url(session, profile_url, rule, filters, allow_deep=False)
            if profile_res.extracted:
                logger.info("Профиль %d дал %d записей", i + 1, len(profile_res.extracted))
                extracted.extend(profile_res.extracted)
            else:
                logger.info("Профиль %d: ничего не найдено", i + 1)

    # Фильтрация или regex fallback
    if extracted:
        result.extracted = parser.apply_filters(extracted, filters)
        logger.info("После ApplyFilters осталось: %d", len(result.extracted))
    else:
        logger.info("CSS и таблицы пусты, запускаем regex fallback")
        fallback = parser.extract_regex_fallback(html)
        result.extracted = parser.apply_basic_filters(fallback)
        logger.info("Fallback дал: %d", len(result.extracted))

    logger.info("Завершено: %s, итого записей: %d", url_str, len(result.extracted))
    return result


async def run_worker(
    worker_id: int,
    queue: asyncio.Queue,
    results_queue: asyncio.Queue,
    cfg: Config,
    semaphore: asyncio.Semaphore,
):
    """Основная функция асинхронного воркера."""
    rule = cfg.task.extract_rules[0] if cfg.task.extract_rules else ExtractRule()
    filters = cfg.task.filters

    async with semaphore:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                res = await process_url(session, url, rule, filters, True)
                await results_queue.put(res)
