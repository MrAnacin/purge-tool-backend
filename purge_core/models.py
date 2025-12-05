"""
Модели данных для бэкенда
"""
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import humanize


class OSPlatform(str, Enum):
    """Поддерживаемые операционные системы"""
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    ALL = "all"


class CleanupCategory(str, Enum):
    """Категории очистки"""
    TEMP_FILES = "temp_files"
    BROWSER_CACHE = "browser_cache"
    BROWSER_COOKIES = "browser_cookies"
    BROWSER_HISTORY = "browser_history"
    SYSTEM_LOGS = "system_logs"
    APPLICATION_LOGS = "application_logs"
    RECYCLE_BIN = "recycle_bin"
    MEMORY_DUMPS = "memory_dumps"
    SOFTWARE_CACHE = "software_cache"
    PACKAGE_CACHE = "package_cache"
    THUMBNAILS = "thumbnails"
    DOWNLOADS = "downloads"
    OTHER = "other"


class SafetyLevel(str, Enum):
    """Уровень безопасности удаления"""
    SAFE = "safe"           # Безопасно, можно удалять автоматически
    WARNING = "warning"     # Требуется предупреждение (кеш, временные файлы)
    DANGEROUS = "dangerous" # Опасно, требует подтверждения (логи, cookies)
    CRITICAL = "critical"   # Критично, лучше не трогать (системные файлы)


class WasteItem(BaseModel):
    """Объект, найденный для очистки"""
    path: Path
    size: int = 0  # в байтах
    category: CleanupCategory
    description: str
    safety_level: SafetyLevel = SafetyLevel.WARNING
    last_accessed: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    owner: Optional[str] = None
    process_locked: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Вычисляемые свойства
    @property
    def human_size(self) -> str:
        """Размер в человекочитаемом формате"""
        return humanize.naturalsize(self.size)
    
    @property
    def extension(self) -> str:
        """Расширение файла"""
        return self.path.suffix.lower()
    
    @property
    def is_file(self) -> bool:
        """Является ли файлом"""
        return self.path.is_file()
    
    @property
    def is_directory(self) -> bool:
        """Является ли директорией"""
        return self.path.is_dir()
    
    @validator('path')
    def validate_path(cls, v):
        """Валидация пути"""
        if not v.is_absolute():
            raise ValueError(f"Path must be absolute: {v}")
        return v


class ScanResult(BaseModel):
    """Результат сканирования системы"""
    scan_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    total_found: int = 0
    total_size: int = 0  # в байтах
    items: List[WasteItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    platform: OSPlatform
    duration: float = 0.0  # в секундах
    
    @property
    def human_total_size(self) -> str:
        """Общий размер в человекочитаемом формате"""
        return humanize.naturalsize(self.total_size)
    
    @property
    def by_category(self) -> Dict[CleanupCategory, List[WasteItem]]:
        """Группировка по категориям"""
        result = {}
        for item in self.items:
            result.setdefault(item.category, []).append(item)
        return result


class CleanupResult(BaseModel):
    """Результат очистки"""
    cleanup_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    total_removed: int = 0
    total_freed: int = 0  # в байтах
    removed_items: List[WasteItem] = Field(default_factory=list)
    failed_items: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    duration: float = 0.0
    
    @property
    def human_freed(self) -> str:
        """Освобождённое место в человекочитаемом формате"""
        return humanize.naturalsize(self.total_freed)


class ScannerConfig(BaseModel):
    """Конфигурация сканера"""
    enabled: bool = True
    priority: int = 10  # Приоритет (меньше = выше)
    max_file_size: Optional[int] = None  # Максимальный размер файла в байтах
    min_file_age_days: int = 1  # Минимальный возраст файла в днях
    exclude_patterns: List[str] = Field(default_factory=list)
    include_patterns: List[str] = Field(default_factory=list)