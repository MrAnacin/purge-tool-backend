"""
Менеджер для управления и запуска сканеров
"""
import logging
import importlib
import pkgutil
from typing import List, Dict, Type, Optional
from pathlib import Path

from .models import ScanResult, CleanupResult, OSPlatform, WasteItem
from .base_scanner import BaseScanner
from .audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class ScannerManager:
    """Менеджер для регистрации и запуска сканеров"""
    
    def __init__(self, scanners_path: Optional[Path] = None):
        self.scanners: List[BaseScanner] = []
        self.audit_logger = AuditLogger()
        
        if scanners_path:
            self._discover_scanners(scanners_path)
    
    def register_scanner(self, scanner: BaseScanner) -> None:
        """Регистрирует сканер"""
        if scanner.is_supported():
            self.scanners.append(scanner)
            logger.debug(f"Registered scanner: {scanner.name}")
        else:
            logger.debug(f"Skipped unsupported scanner: {scanner.name}")
    
    def register_scanner_class(self, scanner_class: Type[BaseScanner], **kwargs) -> None:
        """Регистрирует сканер по классу"""
        scanner = scanner_class(**kwargs)
        self.register_scanner(scanner)
    
    def scan_system(self, scanner_names: Optional[List[str]] = None) -> ScanResult:
        """
        Сканирует систему всеми зарегистрированными сканерами
        """
        from .models import ScanResult
        import time
        
        start_time = time.time()
        result = ScanResult(
            scan_id=self._generate_id(),
            platform=self._detect_platform(),
        )
        
        scanners_to_run = self._filter_scanners(scanner_names)
        
        for scanner in scanners_to_run:
            try:
                logger.info(f"Running scanner: {scanner.name}")
                items = scanner.scan()
                result.items.extend(items)
                logger.info(f"Scanner {scanner.name} found {len(items)} items")
            except Exception as e:
                error_msg = f"Scanner {scanner.name} failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)
        
        # Подсчитываем итоги
        result.total_found = len(result.items)
        result.total_size = sum(item.size for item in result.items)
        result.duration = time.time() - start_time
        
        # Логируем результат сканирования
        self.audit_logger.log_scan(result)
        
        logger.info(f"Scan completed: found {result.total_found} items, "
                   f"total size {result.human_total_size}")
        
        return result
    
    def cleanup(self, items: List[WasteItem], 
                dry_run: bool = False) -> CleanupResult:
        """
        Очищает выбранные объекты
        """
        import time
        from collections import defaultdict
        
        start_time = time.time()
        result = CleanupResult(
            cleanup_id=self._generate_id(),
        )
        
        if dry_run:
            logger.info("Dry run mode - no files will be deleted")
            result.removed_items = items
            result.total_removed = len(items)
            result.total_freed = sum(item.size for item in items)
            result.duration = time.time() - start_time
            return result
        
        # Группируем по сканерам
        items_by_scanner = defaultdict(list)
        for item in items:
            # Находим подходящий сканер по категории
            for scanner in self.scanners:
                if scanner.get_category() == item.category:
                    items_by_scanner[scanner].append(item)
                    break
        
        # Запускаем очистку для каждого сканера
        for scanner, scanner_items in items_by_scanner.items():
            try:
                removed_paths = scanner.cleanup(scanner_items)
                result.removed_items.extend(
                    item for item in scanner_items 
                    if item.path in removed_paths
                )
                
                # Собираем неудачные попытки
                for item in scanner_items:
                    if item.path not in removed_paths:
                        result.failed_items.append({
                            'path': str(item.path),
                            'error': 'Cleanup failed',
                            'scanner': scanner.name
                        })
                        
            except Exception as e:
                error_msg = f"Cleanup failed for scanner {scanner.name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)
        
        # Подсчитываем итоги
        result.total_removed = len(result.removed_items)
        result.total_freed = sum(item.size for item in result.removed_items)
        result.duration = time.time() - start_time
        
        # Логируем результат очистки
        self.audit_logger.log_cleanup(result)
        
        logger.info(f"Cleanup completed: removed {result.total_removed} items, "
                   f"freed {result.human_freed}")
        
        return result
    
    def get_scanner_info(self) -> List[Dict]:
        """Возвращает информацию о всех сканерах"""
        info = []
        for scanner in self.scanners:
            info.append({
                'name': scanner.name,
                'category': scanner.get_category(),
                'description': scanner.description,
                'enabled': scanner.config.enabled,
                'supported': scanner.is_supported(),
                'platforms': [p.value for p in scanner.get_supported_platforms()],
            })
        return info
    
    def _filter_scanners(self, scanner_names: Optional[List[str]] = None) -> List[BaseScanner]:
        """Фильтрует сканеры по именам"""
        if not scanner_names:
            return [s for s in self.scanners if s.config.enabled]
        
        filtered = []
        for scanner in self.scanners:
            if scanner.name in scanner_names and scanner.config.enabled:
                filtered.append(scanner)
        return filtered
    
    def _discover_scanners(self, scanners_path: Path) -> None:
        """Автоматически обнаруживает и регистрирует сканеры в папке"""
        if not scanners_path.exists():
            logger.warning(f"Scanners path does not exist: {scanners_path}")
            return
        
        # Преобразуем путь в Python-модуль
        import sys
        scanners_dir = str(scanners_path.parent)
        if scanners_dir not in sys.path:
            sys.path.insert(0, scanners_dir)
        
        module_name = scanners_path.name
        
        try:
            module = importlib.import_module(module_name)
            
            for _, name, ispkg in pkgutil.iter_modules(module.__path__, module.__name__ + '.'):
                if not ispkg:
                    submodule = importlib.import_module(name)
                    
                    # Ищем классы-наследники BaseScanner
                    for attr_name in dir(submodule):
                        attr = getattr(submodule, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseScanner) and 
                            attr != BaseScanner):
                            
                            self.register_scanner_class(attr)
                            logger.debug(f"Discovered scanner: {attr_name}")
                            
        except ImportError as e:
            logger.error(f"Failed to discover scanners: {e}")
    
    def _generate_id(self) -> str:
        """Генерирует уникальный ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _detect_platform(self) -> OSPlatform:
        """Определяет текущую платформу"""
        import platform
        system = platform.system().lower()
        if system == 'windows':
            return OSPlatform.WINDOWS
        elif system == 'linux':
            return OSPlatform.LINUX
        elif system == 'darwin':
            return OSPlatform.MACOS
        else:
            raise ValueError(f"Unsupported platform: {system}")