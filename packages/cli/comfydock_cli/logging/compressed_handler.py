"""Dual-output rotating file handler with real-time log compression."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .log_compressor import LogCompressor


class CompressedDualHandler(RotatingFileHandler):
    """File handler that writes both full and compressed logs simultaneously.

    Writes to:
    - full.log: Complete verbose logs with rotation
    - compressed.log: Real-time compressed version

    The compressed log uses a lighter format optimized for token count reduction
    while preserving all semantic content.
    """

    def __init__(
        self,
        log_dir: Path,
        env_name: str,
        compression_level: str = 'medium',
        maxBytes: int = 10 * 1024 * 1024,
        backupCount: int = 5,
        encoding: str = 'utf-8'
    ):
        """Initialize dual-output handler.

        Args:
            log_dir: Directory for log files (e.g., workspace/logs/test1/)
            env_name: Environment name (for header comments)
            compression_level: Compression level (light, medium, aggressive)
            maxBytes: Max size before rotation (applies to full.log)
            backupCount: Number of backup files to keep
            encoding: File encoding
        """
        # Ensure log directory exists
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Initialize base handler for full.log
        full_log = log_dir / 'full.log'
        super().__init__(full_log, maxBytes=maxBytes, backupCount=backupCount, encoding=encoding)

        # Open compressed.log
        self.compressed_path = log_dir / 'compressed.log'
        self.compressed_file = open(self.compressed_path, 'a', encoding=encoding)

        # Initialize compressor
        self.compressor = LogCompressor(compression_level=compression_level)

        # Write header to compressed log
        self._write_compressed_header(env_name, compression_level)

    def _write_compressed_header(self, env_name: str, level: str) -> None:
        """Write header to compressed log file."""
        from datetime import datetime
        self.compressed_file.write(f"# Compressed logs for environment: {env_name}\n")
        self.compressed_file.write(f"# Compression level: {level}\n")
        self.compressed_file.write(f"# Session started: {datetime.now().isoformat()}\n")
        self.compressed_file.write("#\n")
        self.compressed_file.flush()

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record to both full and compressed logs.

        Args:
            record: Log record to emit
        """
        try:
            # Write to full.log via parent handler
            super().emit(record)

            # Format the record for compression
            formatted = self.format(record)

            # Compress and write to compressed.log
            compressed = self.compressor.compress_record(formatted)
            if compressed:  # Empty string means skip this line
                self.compressed_file.write(compressed + '\n')
                self.compressed_file.flush()

        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close both log files and write dictionary."""
        try:
            # Write module dictionary to compressed log
            dictionary = self.compressor.get_dictionary()
            if dictionary:
                self.compressed_file.write(dictionary)

            # Close compressed file
            self.compressed_file.close()

            # Close full log via parent
            super().close()

        except Exception:
            # Ensure we don't break on cleanup
            pass
