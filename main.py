"""Многопоточное консольное приложение для массового сбора контактных данных."""

import asyncio
import json
import logging
from typing import List, Dict

from internal.config.dsl import load_config
from internal.engine.worker import run_worker
from internal.metrics.monitor import Monitor

# Настройка логирования
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
worker_formatter = logging.Formatter("[WORKER] %(asctime)s %(message)s")

# Общий лог (crawler.log)
crawler_handler = logging.FileHandler("crawler.log", encoding="utf-8", mode="w")
crawler_handler.setFormatter(formatter)

# Лог воркеров (worker.log)
worker_handler = logging.FileHandler("worker.log", encoding="utf-8", mode="w")
worker_handler.setFormatter(worker_formatter)

# Root logger (только в файл, как в Go)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(crawler_handler)

# Worker logger
worker_logger = logging.getLogger("worker")
worker_logger.setLevel(logging.INFO)
worker_logger.addHandler(worker_handler)
worker_logger.propagate = False

logger = logging.getLogger(__name__)


def load_urls(path: str) -> List[str]:
    """Считывает список адресов из текстового файла."""
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def save_results_to_json(file_path: str, data: List[Dict[str, str]]) -> None:
    """Сохраняет срез результатов в JSON-файл с человекочитаемым форматированием."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def main() -> None:
    monitor = Monitor()
    logger.info(">>> Запуск экспериментального краулера на Python...")
    print(">>> Запуск экспериментального краулера на Python...")

    cfg = load_config("configs/rules.yaml")
    logger.info(">>> Конфигурация '%s' успешно загружена", cfg.task.name)
    print(f">>> Конфигурация '{cfg.task.name}' успешно загружена")

    urls = load_urls("data/urls.txt")
    logger.info(">>> Подготовлено задач: %d", len(urls))
    print(f">>> Подготовлено задач: {len(urls)}")

    if not urls:
        logger.info(">>> Нет URL для обработки. Завершение.")
        print(">>> Нет URL для обработки. Завершение.")
        return

    # Настройка конкурентности
    num_workers = 40
    queue = asyncio.Queue()
    results_queue = asyncio.Queue()

    for url in urls:
        await queue.put(url)

    semaphore = asyncio.Semaphore(num_workers)

    # Запуск пула воркеров
    workers = [
        asyncio.create_task(run_worker(i + 1, queue, results_queue, cfg, semaphore))
        for i in range(num_workers)
    ]

    # Ожидание завершения всех воркеров (исключения не прерывают работу остальных)
    await asyncio.gather(*workers, return_exceptions=True)

    # Сбор статистики
    success_count = 0
    error_count = 0
    all_extracted_data: List[Dict[str, str]] = []

    while not results_queue.empty():
        res = await results_queue.get()
        if res.error:
            error_count += 1
            logger.error("[ОШИБКА] %s: %s", res.url, res.error)
        else:
            success_count += 1
            if res.extracted:
                logger.info("[УСПЕХ] %s -> Найдено контактов: %d", res.url, len(res.extracted))
                print(f"[УСПЕХ] {res.url} -> Найдено контактов: {len(res.extracted)}")
                all_extracted_data.extend(res.extracted)
            else:
                logger.warning("[ПРЕДУПРЕЖДЕНИЕ] %s -> Страница загружена, но по селекторам ничего не найдено", res.url)
                print(f"[ПРЕДУПРЕЖДЕНИЕ] {res.url} -> Страница загружена, но по селекторам ничего не найдено")

    output_file = "data/results.json"
    try:
        save_results_to_json(output_file, all_extracted_data)
        logger.info(">>> Данные успешно сохранены в файл: %s", output_file)
        print(f"\n>>> Данные успешно сохранены в файл: {output_file}")
    except OSError as e:
        logger.error("Не удалось сохранить результаты в файл: %s", e)

    monitor.stop()
    logger.info("Статистика обхода: Успешно: %d | Ошибок: %d | Записей сохранено: %d", success_count, error_count, len(all_extracted_data))
    print(f"\nСтатистика обхода: Успешно: {success_count} | Ошибок: {error_count} | Записей сохранено: {len(all_extracted_data)}")
    monitor.get_report()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прервано пользователем (Ctrl+C)")
    except Exception:
        logger.critical("Критическая ошибка", exc_info=True)
        raise
