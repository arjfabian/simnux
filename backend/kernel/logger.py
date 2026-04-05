import os
from datetime import datetime

class Logger:
    def __init__(self, log_dir: str = "logs", filename: str = "simnux.log"):
        # We make sure the logs folder exists in the backend
        self.log_path = os.path.join(os.getcwd(), log_dir)
        os.makedirs(self.log_path, exist_ok=True)
        self.log_file = os.path.join(self.log_path, filename)

    def add(self, message: str, level: str = "INFO"):
        """Writes a message in the log with timestamp and level."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}\n"
        
        # We use 'a' (append) so the contents are preserved
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(formatted_message)
        
        # Optionally, we display it in the console
        print(formatted_message.strip())

    def error(self, message: str):
        self.add(message, level="ERROR")

    def warn(self, message: str):
        self.add(message, level="WARNING")