"""Excel cases: scenario-local preparation, verification and cleanup."""
import pytest
from common.config import EXCEL_CONFIG
from common.cases import load_workbook_cases
from common.executor import execute_case

CASES = load_workbook_cases(EXCEL_CONFIG["file_path"])

@pytest.mark.integration
@pytest.mark.parametrize("gateway_case", CASES, ids=[c["case_id"] for c in CASES], indirect=True)
def test_gateway_case(gateway_case):
    execute_case(gateway_case)
