"""
Базовый класс для всех сканеров
"""
import abc
import fnmatch
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Generator
from .models import WasteItem, CleanupCategory, SafetyLevel, ScannerConfig, OSPlatform
import platform
import psutil

logger = logging.getLogger(__name__)


class BaseScanner(abc.ABC):
    """Абстрактный базовый класс сканера"""
    
    def __init__(self, config: Optional[ScannerConfig] = None):
        self.config = config or ScannerConfig()
        self._current_platform = self._detect_platform()
        self.name = self.__class__.__name__
        
    @abc.abstractmethod
    def get_supported_platforms(self) -> List[OSPlatform]:
        """Возвращает список поддерживаемых платформ"""
        pass
    
    @abc.abstractmethod
    def get_category(self) -> CleanupCategory:
        """Возвращает категорию сканера"""
        pass
    
    @abc.abstractproperty
    def description(self) -> str:
        """Описание сканера"""
        pass
    
    def is_supported(self) -> bool:
        """Проверяет, поддерживается ли сканер на текущей платформе"""
        supported = self.get_supported_platforms()
        return OSPlatform.ALL in supported or self._current_platform in supported
    
    def scan(self) -> List[WasteItem]:
        """
        Основной метод сканирования.
        Возвращает список найденных объектов.
        """
        if not self.is_supported():
            logger.debug(f"Scanner {self.name} not supported on {self._current_platform}")
            return []
        
        if not self.config.enabled:
            logger.debug(f"Scanner {self.name} is disabled")
            return []
        
        logger.info(f"Starting scanner: {self.name}")
        items = []
        
        try:
            for item in self._scan_implementation():
                if self._should_include(item):
                    items.append(item)
        except Exception as e:
            logger.error(f"Scanner {self.name} failed: {e}", exc_info=True)
        
        logger.info(f"Scanner {self.name} found {len(items)} items")
        return items
    
    @abc.abstractmethod
    def _scan_implementation(self) -> Generator[WasteItem, None, None]:
        """Реализация сканирования (генератор)"""
        pass
    
    def cleanup(self, items: List[WasteItem]) -> List[Path]:
        """
        Очистка найденных объектов.
        Возвращает список успешно удалённых путей.
        """
        if not self.is_supported():
            return []
        
        removed = []
        for item in items:
            try:
                if self._safe_remove(item.path):
                    removed.append(item.path)
                    logger.info(f"Removed: {item.path}")
            except Exception as e:
                logger.error(f"Failed to remove {item.path}: {e}")
        
        return removed
    
    def _should_include(self, item: WasteItem) -> bool:
        """Проверяет, должен ли объект быть включен в результат"""
        # Проверка возраста файла
        if item.last_modified:
            min_age = datetime.now() - timedelta(days=self.config.min_file_age_days)
            if item.last_modified > min_age:
                return False
        
        # Проверка размера
        if self.config.max_file_size and item.size > self.config.max_file_size:
            return False
        
        # Проверка исключений по шаблонам
        path_str = str(item.path)
        for pattern in self.config.exclude_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return False
        
        # Проверка включений по шаблонам
        if self.config.include_patterns:
            for pattern in self.config.include_patterns:
                if fnmatch.fnmatch(path_str, pattern):
                    return True
            return False
        
        return True
    
    def _safe_remove(self, path: Path) -> bool:
        """Безопасное удаление файла или директории"""
        if not path.exists():
            return False
        
        # Проверка, используется ли файл процессом
        if self._is_file_locked(path):
            logger.warning(f"File is locked by process: {path}")
            return False
        
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                # Рекурсивное удаление директории
                for child in path.rglob('*'):
                    if child.is_file():
                        child.unlink()
                path.rmdir()
            return True
        except PermissionError:
            logger.error(f"Permission denied: {path}")
            return False
        except OSError as e:
            logger.error(f"OS error removing {path}: {e}")
            return False
    
    def _is_file_locked(self, path: Path) -> bool:
        """Проверяет, заблокирован ли файл процессом"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                try:
                    files = proc.info.get('open_files')
                    if files:
                        for f in files:
                            if Path(f.path) == path:
                                return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        
        return False
    
    def _detect_platform(self) -> OSPlatform:
        """Определяет текущую платформу"""
        system = platform.system().lower()
        if system == 'windows':
            return OSPlatform.WINDOWS
        elif system == 'linux':
            return OSPlatform.LINUX
        elif system == 'darwin':
            return OSPlatform.MACOS
        else:
            raise ValueError(f"Unsupported platform: {system}")
    
    def _get_file_info(self, path: Path) -> Optional[dict]:
        """Получает информацию о файле"""
        try:
            stat = path.stat()
            return {
                'size': stat.st_size,
                'last_accessed': datetime.fromtimestamp(stat.st_atime),
                'last_modified': datetime.fromtimestamp(stat.st_mtime),
                'owner': path.owner() if hasattr(path, 'owner') else None,
            }
        except (OSError, PermissionError):
            return None