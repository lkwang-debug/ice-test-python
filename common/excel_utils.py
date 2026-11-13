"""Compatibility facade for callers using the old ExcelUtils class."""
from pathlib import Path
from common.config import EXCEL_CONFIG
from common.cases import load_workbook_cases


class ExcelUtils:
    def __init__(self):
        self.file_path = Path(EXCEL_CONFIG["file_path"])
        self.skipped_count = 0
        self.error_count = 0
        self.wb = None
        if not self.file_path.is_file():
            raise FileNotFoundError(self.file_path)

    def get_test_cases(self):
        return load_workbook_cases(self.file_path)

    def close(self):
        if self.wb:
            self.wb.close()
            self.wb = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
