from datetime import datetime
import threading

class SystemLogger:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SystemLogger, cls).__new__(cls)
                cls._instance.logs = []
                cls._instance.max_logs = 100
        return cls._instance

    def log(self, message, category="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "time": timestamp,
            "msg": message,
            "type": category
        }
        with self._lock:
            self.logs.append(log_entry)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)
        
        # Also print to terminal
        print(f"[{timestamp}] {message}")

    def get_logs(self):
        with self._lock:
            return list(self.logs)

# Global Instance
sys_logger = SystemLogger()

def web_log(msg, category="info"):
    sys_logger.log(msg, category)
