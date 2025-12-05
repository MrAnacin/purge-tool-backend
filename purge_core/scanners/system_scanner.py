"""
Сканер системных временных файлов и логов
"""
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Generator
import platform

from ..base_scanner import BaseScanner
from ..models import WasteItem, CleanupCategory, SafetyLevel, OSPlatform
from platformdirs import user_cache_dir, user_log_dir, site_cache_dir


class SystemTempScanner(BaseScanner):
    """Сканер системных временных файлов"""
    
    def get_supported_platforms(self) -> List[OSPlatform]:
        return [OSPlatform.ALL]
    
    def get_category(self) -> CleanupCategory:
        return CleanupCategory.TEMP_FILES
    
    @property
    def description(self) -> str:
        return "System temporary files and cache"
    
    def _scan_implementation(self) -> Generator[WasteItem, None, None]:
        """Сканирует системные временные файлы"""
        
        # Пользовательские временные файлы
        temp_dirs = [
            Path(tempfile.gettempdir()),
            Path(user_cache_dir()),
        ]
        
        # Добавляем системные пути в зависимости от ОС
        system = platform.system().lower()
        if system == 'windows':
            temp_dirs.extend([
                Path(r'C:\Windows\Temp'),
                Path(r'C:\Windows\Prefetch'),
            ])
        elif system == 'linux':
            temp_dirs.extend([
                Path('/var/tmp'),
                Path('/var/cache'),
                Path.home() / '.cache',
            ])
        elif system == 'darwin':
            temp_dirs.extend([
                Path.home() / 'Library/Caches',
                Path('/Library/Caches'),
                Path('/System/Library/Caches'),
            ])
        
        for temp_dir in temp_dirs:
            if temp_dir.exists() and temp_dir.is_dir():
                yield from self._scan_directory(temp_dir, "System temporary files")
    
    def _scan_directory(self, directory: Path, description: str) -> Generator[WasteItem, None, None]:
        """Рекурсивно сканирует директорию"""
        try:
            for item in directory.iterdir():
                try:
                    if item.is_file():
                        file_info = self._get_file_info(item)
                        if file_info:
                            yield WasteItem(
                                path=item,
                                size=file_info['size'],
                                category=self.get_category(),
                                description=f"{description}: {item.name}",
                                safety_level=SafetyLevel.SAFE,
                                last_accessed=file_info['last_accessed'],
                                last_modified=file_info['last_modified'],
                                owner=file_info['owner'],
                            )
                    elif item.is_dir():
                        # Рекурсивно сканируем поддиректории
                        yield from self._scan_directory(item, description)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass


class SystemLogsScanner(BaseScanner):
    """Сканер системных логов"""
    
    def get_supported_platforms(self) -> List[OSPlatform]:
        return [OSPlatform.ALL]
    
    def get_category(self) -> CleanupCategory:
        return CleanupCategory.SYSTEM_LOGS
    
    @property
    def description(self) -> str:
        return "System and application log files"
    
    def _scan_implementation(self) -> Generator[WasteItem, None, None]:
        """Сканирует логи"""
        log_dirs = [Path(user_log_dir())]
        
        system = platform.system().lower()
        if system == 'windows':
            log_dirs.extend([
                Path(r'C:\Windows\Logs'),
                Path(r'C:\Windows\System32\winevt\Logs'),
            ])
        elif system == 'linux':
            log_dirs.extend([
                Path('/var/log'),
                Path.home() / '.local/share/applications/logs',
            ])
        elif system == 'darwin':
            log_dirs.extend([
                Path.home() / 'Library/Logs',
                Path('/Library/Logs'),
                Path('/var/log'),
            ])
        
        for log_dir in log_dirs:
            if log_dir.exists() and log_dir.is_dir():
                yield from self._scan_log_directory(log_dir)
    
    def _scan_log_directory(self, directory: Path) -> Generator[WasteItem, None, None]:
        """Сканирует директорию с логами"""
        try:
            for item in directory.rglob('*.log'):
                if item.is_file():
                    file_info = self._get_file_info(item)
                    if file_info:
                        # Старые логи (старше 30 дней) считаем безопасными
                        age = datetime.now() - file_info['last_modified']
                        safety = SafetyLevel.SAFE if age.days > 30 else SafetyLevel.WARNING
                        
                        yield WasteItem(
                            path=item,
                            size=file_info['size'],
                            category=self.get_category(),
                            description=f"Log file: {item.relative_to(directory.parent)}",
                            safety_level=safety,
                            last_accessed=file_info['last_accessed'],
                            last_modified=file_info['last_modified'],
                            owner=file_info['owner'],
                        )
        except (PermissionError, OSError):
            pass