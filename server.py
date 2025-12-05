"""
JSON-RPC сервер для взаимодействия с Rust-фронтендом
"""
import sys
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent))

from purge_core.scanner_manager import ScannerManager
from purge_core.models import WasteItem, CleanupCategory
from purge_core.scanners.system_scanner import SystemTempScanner, SystemLogsScanner
from purge_core.scanners.browser_scanner import ChromeScanner, FirefoxScanner


class JSONRPCServer:
    """Простой JSON-RPC сервер для IPC через stdin/stdout"""
    
    def __init__(self):
        self.manager = ScannerManager()
        self._register_scanners()
        self._handlers = {
            'ping': self.handle_ping,
            'scan': self.handle_scan,
            'cleanup': self.handle_cleanup,
            'get_scanners': self.handle_get_scanners,
            'get_scan_results': self.handle_get_scan_results,
        }
        self.last_scan_result = None
        
    def _register_scanners(self):
        """Регистрирует все сканеры"""
        self.manager.register_scanner_class(SystemTempScanner)
        self.manager.register_scanner_class(SystemLogsScanner)
        self.manager.register_scanner_class(ChromeScanner)
        self.manager.register_scanner_class(FirefoxScanner)
        
        logging.info(f"Registered {len(self.manager.scanners)} scanners")
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Обрабатывает JSON-RPC запрос"""
        try:
            method = request.get('method')
            params = request.get('params', {})
            request_id = request.get('id')
            
            if method not in self._handlers:
                return self._error_response(request_id, -32601, "Method not found")
            
            handler = self._handlers[method]
            result = handler(params)
            
            return self._success_response(request_id, result)
            
        except Exception as e:
            logging.error(f"Error handling request: {e}", exc_info=True)
            return self._error_response(request.get('id'), -32603, str(e))
    
    def handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Проверка доступности сервера"""
        return {'status': 'ok', 'message': 'pong'}
    
    def handle_scan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Запуск сканирования"""
        scanner_names = params.get('scanner_names')
        
        logging.info(f"Starting scan with scanners: {scanner_names}")
        result = self.manager.scan_system(scanner_names)
        
        # Сохраняем результат для возможного последующего использования
        self.last_scan_result = result
        
        # Конвертируем в словарь
        result_dict = result.model_dump()
        
        # Конвертируем Path объекты в строки
        def convert_paths(obj):
            if isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            else:
                return obj
        
        result_dict = convert_paths(result_dict)
        return result_dict
    
    def handle_cleanup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Запуск очистки"""
        items_data = params.get('items', [])
        dry_run = params.get('dry_run', False)
        
        # Восстанавливаем WasteItem объекты из словарей
        items = []
        for item_data in items_data:
            # Конвертируем строки пути обратно в Path
            if 'path' in item_data:
                item_data['path'] = Path(item_data['path'])
            items.append(WasteItem(**item_data))
        
        logging.info(f"Starting cleanup for {len(items)} items, dry_run={dry_run}")
        result = self.manager.cleanup(items, dry_run=dry_run)
        
        # Конвертируем в словарь
        result_dict = result.model_dump()
        
        # Конвертируем Path объекты в строки
        def convert_paths(obj):
            if isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            else:
                return obj
        
        result_dict = convert_paths(result_dict)
        return result_dict
    
    def handle_get_scanners(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Получение информации о сканерах"""
        return self.manager.get_scanner_info()
    
    def handle_get_scan_results(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Получение последних результатов сканирования"""
        if self.last_scan_result:
            result_dict = self.last_scan_result.model_dump()
            
            # Конвертируем Path объекты в строки
            def convert_paths(obj):
                if isinstance(obj, Path):
                    return str(obj)
                elif isinstance(obj, dict):
                    return {k: convert_paths(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_paths(item) for item in obj]
                else:
                    return obj
            
            return convert_paths(result_dict)
        return None
    
    def _success_response(self, request_id: Optional[str], result: Any) -> Dict[str, Any]:
        """Формирует успешный ответ"""
        return {
            'jsonrpc': '2.0',
            'id': request_id,
            'result': result
        }
    
    def _error_response(self, request_id: Optional[str], 
                       code: int, message: str) -> Dict[str, Any]:
        """Формирует ответ с ошибкой"""
        return {
            'jsonrpc': '2.0',
            'id': request_id,
            'error': {
                'code': code,
                'message': message
            }
        }


def main():
    """Основная функция сервера"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('purge_server.log'),
            logging.StreamHandler()
        ]
    )
    
    server = JSONRPCServer()
    logging.info("Purge Tool JSON-RPC server started")
    logging.info("Listening on stdin/stdout")
    
    # Чтение из stdin, запись в stdout
    while True:
        try:
            # Читаем строку из stdin
            line = sys.stdin.readline()
            if not line:
                break
            
            # Парсим JSON запрос
            request = json.loads(line.strip())
            logging.debug(f"Received request: {request}")
            
            # Обрабатываем запрос
            response = server.handle_request(request)
            
            # Отправляем ответ
            json_response = json.dumps(response)
            sys.stdout.write(json_response + '\n')
            sys.stdout.flush()
            
            logging.debug(f"Sent response: {response}")
            
        except json.JSONDecodeError as e:
            error_response = {
                'jsonrpc': '2.0',
                'id': None,
                'error': {
                    'code': -32700,
                    'message': f'Parse error: {str(e)}'
                }
            }
            sys.stdout.write(json.dumps(error_response) + '\n')
            sys.stdout.flush()
            
        except KeyboardInterrupt:
            logging.info("Server shutdown requested")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}", exc_info=True)
            error_response = {
                'jsonrpc': '2.0',
                'id': None,
                'error': {
                    'code': -32603,
                    'message': f'Internal error: {str(e)}'
                }
            }
            sys.stdout.write(json.dumps(error_response) + '\n')
            sys.stdout.flush()
    
    logging.info("Server stopped")


if __name__ == "__main__":
    main()