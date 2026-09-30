from claudarama.scenario.validator import Scenario, ScenarioChecks
from claudarama.scenario.runner import ScenarioRunner

def test_scenario_runner_multi_step():
    scenario = Scenario(
        name="multi",
        role="eng",
        prompt="start",
        steps=[
            {"type": "mock_llm_turns", "turns": [{"call": "tool", "result": "res"}]},
            {"type": "ceo_action", "input": "YES"},
        ],
        checks=ScenarioChecks(includes=["CEO ACTION: YES"])
    )
    runner = ScenarioRunner()
    res = runner.run(scenario)
    assert res.passed
    assert runner.mock_turns_yielded == [[{"call": "tool", "result": "res"}]]
    assert runner.ceo_inputs == ["YES"]
