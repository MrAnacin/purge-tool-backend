"""
Сканер кеша и данных браузеров
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Generator, Optional, Dict, Any

from ..base_scanner import BaseScanner
from ..models import WasteItem, CleanupCategory, SafetyLevel, OSPlatform
from platformdirs import user_data_dir, user_cache_dir


class BrowserScanner(BaseScanner):
    """Базовый класс для сканеров браузеров"""
    
    def __init__(self, browser_name: str, **kwargs):
        super().__init__(**kwargs)
        self.browser_name = browser_name
    
    def get_category(self) -> CleanupCategory:
        return CleanupCategory.BROWSER_CACHE
    
    @property
    def description(self) -> str:
        return f"{self.browser_name} browser data"
    
    def _get_browser_paths(self) -> List[Path]:
        """Возвращает пути к данным браузера (переопределяется в наследниках)"""
        return []
    
    def _scan_implementation(self) -> Generator[WasteItem, None, None]:
        """Сканирует данные браузера"""
        for browser_path in self._get_browser_paths():
            if browser_path.exists():
                # Сканируем различные типы данных браузера
                yield from self._scan_cache(browser_path)
                yield from self._scan_cookies(browser_path)
                yield from self._scan_history(browser_path)
    
    def _scan_cache(self, browser_path: Path) -> Generator[WasteItem, None, None]:
        """Сканирует кеш браузера"""
        cache_dirs = [
            browser_path / 'Cache',
            browser_path / 'Code Cache',
            browser_path / 'GPUCache',
            browser_path / 'ShaderCache',
            browser_path / 'Service Worker',
        ]
        
        for cache_dir in cache_dirs:
            if cache_dir.exists() and cache_dir.is_dir():
                yield from self._scan_cache_directory(cache_dir)
    
    def _scan_cache_directory(self, directory: Path) -> Generator[WasteItem, None, None]:
        """Сканирует директорию кеша"""
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    file_info = self._get_file_info(item)
                    if file_info:
                        yield WasteItem(
                            path=item,
                            size=file_info['size'],
                            category=CleanupCategory.BROWSER_CACHE,
                            description=f"{self.browser_name} cache file",
                            safety_level=SafetyLevel.SAFE,
                            last_accessed=file_info['last_accessed'],
                            last_modified=file_info['last_modified'],
                            owner=file_info['owner'],
                            metadata={'browser': self.browser_name, 'type': 'cache'}
                        )
        except (PermissionError, OSError):
            pass
    
    def _scan_cookies(self, browser_path: Path) -> Generator[WasteItem, None, None]:
        """Сканирует cookies браузера"""
        cookies_files = [
            browser_path / 'Cookies',
            browser_path / 'Network' / 'Cookies',
        ]
        
        for cookies_file in cookies_files:
            if cookies_file.exists() and cookies_file.is_file():
                file_info = self._get_file_info(cookies_file)
                if file_info:
                    yield WasteItem(
                        path=cookies_file,
                        size=file_info['size'],
                        category=CleanupCategory.BROWSER_COOKIES,
                        description=f"{self.browser_name} cookies database",
                        safety_level=SafetyLevel.DANGEROUS,  # Cookies могут быть важны
                        last_accessed=file_info['last_accessed'],
                        last_modified=file_info['last_modified'],
                        owner=file_info['owner'],
                        metadata={'browser': self.browser_name, 'type': 'cookies'}
                    )
    
    def _scan_history(self, browser_path: Path) -> Generator[WasteItem, None, None]:
        """Сканирует историю браузера"""
        history_files = [
            browser_path / 'History',
            browser_path / 'places.sqlite',  # Firefox
        ]
        
        for history_file in history_files:
            if history_file.exists() and history_file.is_file():
                file_info = self._get_file_info(history_file)
                if file_info:
                    yield WasteItem(
                        path=history_file,
                        size=file_info['size'],
                        category=CleanupCategory.BROWSER_HISTORY,
                        description=f"{self.browser_name} history database",
                        safety_level=SafetyLevel.WARNING,
                        last_accessed=file_info['last_accessed'],
                        last_modified=file_info['last_modified'],
                        owner=file_info['owner'],
                        metadata={'browser': self.browser_name, 'type': 'history'}
                    )


class ChromeScanner(BrowserScanner):
    """Сканер для Google Chrome/Chromium"""
    
    def __init__(self, **kwargs):
        super().__init__("Chrome", **kwargs)
    
    def get_supported_platforms(self) -> List[OSPlatform]:
        return [OSPlatform.WINDOWS, OSPlatform.LINUX, OSPlatform.MACOS]
    
    def _get_browser_paths(self) -> List[Path]:
        paths = []
        system = platform.system().lower()
        
        if system == 'windows':
            chrome_paths = [
                Path(user_data_dir()) / 'Google' / 'Chrome' / 'User Data' / 'Default',
                Path(user_data_dir()) / 'Google' / 'Chrome' / 'User Data' / 'Profile *',
                Path(user_data_dir()) / 'Chromium' / 'User Data' / 'Default',
            ]
        elif system == 'linux':
            chrome_paths = [
                Path.home() / '.config' / 'google-chrome' / 'Default',
                Path.home() / '.config' / 'google-chrome' / 'Profile *',
                Path.home() / '.config' / 'chromium' / 'Default',
            ]
        elif system == 'darwin':
            chrome_paths = [
                Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome' / 'Default',
                Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome' / 'Profile *',
            ]
        else:
            return paths
        
        # Расширяем шаблоны
        import glob
        expanded_paths = []
        for path_pattern in chrome_paths:
            expanded_paths.extend([Path(p) for p in glob.glob(str(path_pattern))])
        
        return expanded_paths


class FirefoxScanner(BrowserScanner):
    """Сканер для Mozilla Firefox"""
    
    def __init__(self, **kwargs):
        super().__init__("Firefox", **kwargs)
    
    def get_supported_platforms(self) -> List[OSPlatform]:
        return [OSPlatform.WINDOWS, OSPlatform.LINUX, OSPlatform.MACOS]
    
    def _get_browser_paths(self) -> List[Path]:
        system = platform.system().lower()
        
        if system == 'windows':
            base_path = Path(user_data_dir()) / 'Mozilla' / 'Firefox' / 'Profiles'
        elif system == 'linux':
            base_path = Path.home() / '.mozilla' / 'firefox'
        elif system == 'darwin':
            base_path = Path.home() / 'Library' / 'Application Support' / 'Firefox' / 'Profiles'
        else:
            return []
        
        if base_path.exists():
            # Ищем профили Firefox
            profiles = []
            for item in base_path.iterdir():
                if item.is_dir() and item.name.endswith('.default-release'):
                    profiles.append(item)
                elif item.is_dir() and '.default' in item.name:
                    profiles.append(item)
            return profiles
        
        return []