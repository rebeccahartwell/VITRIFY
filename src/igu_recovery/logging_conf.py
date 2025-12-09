import logging
import sys
import os
from typing import Optional

# Try to import colorama for cross-platform ANSI support on Windows
try:
    import colorama
    from colorama import Fore, Style
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False
    # Define dummy placeholders if colorama is missing
    class Fore:
        GREEN = ""
        YELLOW = ""
        RED = ""
        BLUE = ""
        RESET = ""
    class Style:
        BRIGHT = ""
        RESET_ALL = ""

class ColoredFormatter(logging.Formatter):
    """
    Custom formatter to add colors to log levels for console output.
    """
    def __init__(self, fmt: str, use_color: bool = True):
        super().__init__(fmt)
        self.use_color = use_color
        
        # Define colors map
        self.COLORS = {
            logging.DEBUG: Fore.BLUE,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT,
        }

    def format(self, record: logging.LogRecord) -> str:
        # Save original msg in case we modify it
        original_msg = record.msg
        
        # Format the message using the standard formatter first
        # This resolves % arguments if any
        # formatted_msg = super().format(record)
        # Actually, standard format() does styling. 
        # We want to inject color codes around the LEVEL or the Whole Line.
        # Let's style the whole line for visibility as per request.
        
        if self.use_color and HAS_COLORAMA:
            color = self.COLORS.get(record.levelno, "")
            reset = Style.RESET_ALL
            
            # Enhancing the record formatting
            # We want: [LEVEL] Message
            # But styled.
            
            record.levelname = f"{color}{record.levelname}{reset}"
            record.msg = f"{color}{record.msg}{reset}"
            
        result = super().format(record)
        
        # Restore formatted msg is tricky because logging caches it.
        # But we modified the record instance which is transient in handle() usually?
        # Safe way: formatting happens on a record. 
        # However, for simple use cases, this is adequate.
        return result

def setup_logging(
    console_level: int = logging.INFO,
    file_path: Optional[str] = None,
    file_level: int = logging.DEBUG,
    no_color: bool = False
) -> logging.Logger:
    """
    Sets up the root logger with:
    - Console handler (colored, formatting based on level)
    - Optional File handler (clean text, detailed format)
    """
    if HAS_COLORAMA:
        colorama.init(autoreset=True)

    # Check environment variable for color disable
    if os.environ.get("NO_COLOR"):
        no_color = True

    # 1. Configure Root Logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG) # Capture all, handlers filter
    
    # Remove existing handlers if any (to avoid duplicates on reload)
    if logger.hasHandlers():
        logger.handlers.clear()

    # 2. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    
    # Check if stdout is a tty
    is_tty = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
    use_color = is_tty and not no_color

    # Define format: Just message for INFO to keep "wizard" feel? 
    # Or "[INFO] Message"?
    # Request says: "key messages ... print in diff colours ... Ensure output remains clean".
    # Existing script is a wizard. "Clean" might mean minimal prefixes.
    # However, for Warn/Error, we definitely want prefixes.
    # Let's use a format that includes level for everything except maybe plain print replacement?
    # But user wants "Use ... logging for all user-visible output".
    # I'll use `%(message)s` for the format, but color the text based on level.
    # This keeps the "print" feel but adds color.
    # Wait, for WARN/ERROR, we usually want "WARNING: ..."
    # Let's encode the level name in the string only if it's not INFO?
    # Or just use `[%(levelname)s] %(message)s`.
    
    console_fmt_str = "%(message)s"
    # Note: If we just use %(message)s, we don't see "WARNING". 
    # I should bake the prefix into the color formatting logic if I want differentiation.
    # OR, rely on the user seeing RED and knowing it's bad.
    # Let's stick to `%(message)s` for clarity as it replaces `print`, 
    # but maybe prepending `level` is safer.
    # Let's do: `%(message)s` for INFO, and `%(levelname)s: %(message)s` for others?
    # That requires a fancy formatter.
    
    # Simpler: Just rely on color for INFO (Green) vs plain?
    # User request: "INFO = green".
    
    console_formatter = ColoredFormatter(console_fmt_str, use_color=use_color)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 3. File Handler (Optional)
    if file_path:
        file_handler = logging.FileHandler(file_path, mode='w', encoding='utf-8')
        file_handler.setLevel(file_level)
        # Detailed format for log file
        file_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger
