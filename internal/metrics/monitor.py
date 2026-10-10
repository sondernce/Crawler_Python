"""Мониторинг времени выполнения и потребления памяти."""

import time
import psutil
import os


class Monitor:
    """Хранит данные о производительности краулера во время эксперимента."""

    def __init__(self):
        self.start_time = time.time()
        self.process = psutil.Process(os.getpid())
        self.start_mem = self.process.memory_info().rss

    def stop(self):
        """Останавливает замер метрик и фиксирует время завершения."""
        self.end_time = time.time()
        self.end_mem = self.process.memory_info().rss

    def get_report(self):
        """Формирует данные для сравнительной таблицы."""
        duration = self.end_time - self.start_time
        alloc_mb = (self.end_mem - self.start_mem) / 1024 / 1024
        current_mb = self.end_mem / 1024 / 1024

        print("\n--- ОТЧЕТ ПО МЕТРИКАМ ПРОИЗВОДИТЕЛЬНОСТИ (Python) ---")
        print(f"Время выполнения цикла: {duration:.2f} сек")
        print(f"Дельта использования RAM: {alloc_mb:.2f} MB")
        print(f"Текущее использование RAM: {current_mb:.2f} MB")
        print(f"Загрузка CPU (средняя): {psutil.cpu_percent(interval=None):.1f}%")
        print("------------------------------------------------")
