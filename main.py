"""
Точка входа для тестирования бэкенда
"""
import sys
import json
from pathlib import Path
from typing import List, Optional

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent))

from purge_core.scanner_manager import ScannerManager
from purge_core.models import WasteItem, CleanupCategory
from purge_core.scanners.system_scanner import SystemTempScanner, SystemLogsScanner
from purge_core.scanners.browser_scanner import ChromeScanner, FirefoxScanner


def setup_logging():
    """Настройка логирования"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('purge_tool.log')
        ]
    )


def main():
    """Основная функция для тестирования"""
    setup_logging()
    
    print("=== Purge Tool Backend Test ===")
    print("Initializing scanner manager...")
    
    # Создаем менеджер
    manager = ScannerManager()
    
    # Регистрируем сканеры
    manager.register_scanner_class(SystemTempScanner)
    manager.register_scanner_class(SystemLogsScanner)
    manager.register_scanner_class(ChromeScanner)
    manager.register_scanner_class(FirefoxScanner)
    
    print(f"Registered {len(manager.scanners)} scanners:")
    for info in manager.get_scanner_info():
        print(f"  - {info['name']}: {info['description']} ({info['category'].value})")
    
    # Запускаем сканирование
    print("\n=== Scanning System ===")
    result = manager.scan_system()
    
    print(f"\nScan completed in {result.duration:.2f}s")
    print(f"Found {result.total_found} items, total size: {result.human_total_size}")
    
    # Группируем по категориям
    by_category = result.by_category
    print("\nBreakdown by category:")
    for category, items in by_category.items():
        total_size = sum(item.size for item in items)
        print(f"  {category.value}: {len(items)} items ({humanize.naturalsize(total_size)})")
    
    # Показываем несколько примеров
    print("\n=== Sample Items ===")
    for i, item in enumerate(result.items[:10]):
        print(f"{i+1}. {item.path.name}")
        print(f"   Size: {item.human_size}, Safety: {item.safety_level.value}")
        print(f"   Desc: {item.description}")
    
    # Пример фильтрации по безопасности
    safe_items = [item for item in result.items if item.safety_level == SafetyLevel.SAFE]
    print(f"\nFound {len(safe_items)} safe items to remove")
    
    # Спросить пользователя о очистке
    if safe_items:
        response = input(f"\nRemove {len(safe_items)} safe items? (y/n): ")
        if response.lower() == 'y':
            print("Starting cleanup...")
            cleanup_result = manager.cleanup(safe_items)
            print(f"Cleanup completed: removed {cleanup_result.total_removed} items")
            print(f"Freed space: {cleanup_result.human_freed}")
    
    # Сохраняем результаты в JSON
    output_file = "scan_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result.model_dump(), f, default=str, indent=2)
    
    print(f"\nResults saved to {output_file}")
    print("=== Test Complete ===")


if __name__ == "__main__":
    # Добавим humanize для красивого вывода размеров
    import humanize
    humanize.activate('ru_RU')  # Для русского языка
    
    main()