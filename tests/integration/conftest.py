from contextlib import contextmanager
import pytest
import allure
from common.scenarios import Scenario
from common.executor import attach


@pytest.fixture
def workflow(gateway_runtime, request):
    @contextmanager
    def create(name, fixture="none", topology="any", requires=None, method="workflow"):
        case = {"case_id": name, "class_name": "workflow", "method": method, "fixture": fixture,
                "topology": topology, "requires": requires or ["write", "database", "room"], "params": {}}
        gateway_runtime.check_case_applicability(case, request.config.getoption("--gateway-scope"))
        scenario = Scenario(gateway_runtime, case)
        allure.dynamic.label("verification", "state")
        allure.dynamic.label("topology", gateway_runtime.topology)
        allure.dynamic.title(name)
        try:
            scenario.prepare()
            yield scenario
        finally:
            try:
                scenario.close()
            except Exception as exc:
                from common.outcomes import label_outcome
                label_outcome("cleanup_failure", str(exc), {"scenario": name})
                attach("Workflow cleanup failure", {"scenario": name, "error": str(exc)})
                raise
    return create
