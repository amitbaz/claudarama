"""The loop scenario drives a real office (issue #85, spec #79 testing seam 1).

``scenarios/loop.json`` is the seam: a ticket that changes how the loop moves adds its scripted
turns, CEO answers and ``checks`` there. This file runs it, says why it failed, and holds the
scenario harness to not passing hollow.
"""
import json
import re
from pathlib import Path

import pytest

from claudarama.scenario import evaluate_scenario, run_scenario_file, validate_scenario

ROOT = Path(__file__).parent.parent


def _why(result) -> str:
    """Why a scenario failed, with everything the office showed on the way."""
    problems = result.validation_errors + result.self_test_errors
    for run in result.turn_results:
        problems += run.error_messages() + ["--- what the office showed ---", run.person_reply]
    return "\n".join(problems)


def _scenario(steps: list[dict], includes: list[str]) -> dict:
    return {"name": "s", "role": "researcher", "prompt": "p", "steps": steps, "checks": {"includes": includes}}


def _walk(steps: list[dict], includes: list[str]):
    """Walk *steps* through a real office and check what it showed."""
    checked = validate_scenario(_scenario(steps, includes))
    assert checked.valid, checked.errors
    return evaluate_scenario(checked.scenario)


def test_the_loop_scenario_walks_a_mandate_from_its_grant_to_closed():
    result = run_scenario_file(ROOT / "scenarios" / "loop.json")

    assert result.passed, _why(result)


def test_a_ceo_answer_with_no_gate_waiting_fails_the_scenario():
    result = _walk([{"type": "ceo_action", "input": "YES"}], includes=["^"])

    assert not result.passed
    assert "the CEO answered YES, but no gate was waiting" in _why(result)


def test_a_turn_the_office_refuses_to_start_shows_the_reason_instead_of_its_calls():
    ungranted = [{"type": "mock_llm_turns", "turns": [{"ticket": "7", "calls": [{"tool": "whoami"}]}]}]

    result = _walk(ungranted, includes=["researcher's turn: refused: ticket '7' is not under a granted mandate"])

    assert result.passed, _why(result)
    assert "researcher calls" not in result.turn_results[0].person_reply


def test_a_turn_that_ends_itself_with_send_still_shows_everything_it_did():
    granted = {"type": "ceo_action", "calls": [
        {"tool": "grant", "args": {"mandate": "M"}}, {"tool": "ticket_ready", "args": {"ticket": "1", "mandate": "M"}},
    ]}
    asks = {"type": "mock_llm_turns", "turns": [{"ticket": "1", "calls": [
        {"tool": "send", "args": {"receiver_id": "pm", "msg_type": "QUESTION", "body": "Which page?", "ticket": "1"}},
        {"run": ["sleep", "0.5"]},
        {"run": ["echo", "still here"]},
    ]}]}

    result = _walk([granted, asks], includes=["researcher runs echo 'still here' -> still here\\nresearcher's turn: done"])

    assert result.passed, _why(result)


def test_a_turn_can_neither_list_nor_answer_a_gate():
    granted = {"type": "ceo_action", "calls": [
        {"tool": "grant", "args": {"mandate": "M"}}, {"tool": "ticket_ready", "args": {"ticket": "1", "mandate": "M"}},
    ]}
    approves_its_own = {"type": "mock_llm_turns", "turns": [{"ticket": "1", "calls": [
        {"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "d.md"}},
        {"tool": "list_gates"},
        {"tool": "answer_gate", "args": {"gate": "diagnosis:M", "answer": "YES"}},
    ]}]}

    result = _walk([granted, approves_its_own], includes=[
        "researcher calls list_gates .* -> REFUSED: .*owner-only",
        "researcher calls answer_gate .* -> REFUSED: .*owner-only",
        "researcher's turn: done\\nMandate 'M': PLANNING, waiting for the CEO",
    ])

    assert result.passed, _why(result)


@pytest.mark.parametrize("step, problem", [
    ({"type": "mock_llm_turns", "turns": [{"role": "eng", "calls": [{"tool": "whoami"}]}]}, "'eng', which is not a Role"),
    ({"type": "mock_llm_turns", "turns": [{"tikcet": "1", "calls": [{"tool": "whoami"}]}]}, "unrecognized fields: tikcet"),
    ({"type": "mock_llm_turns", "turns": [{"calls": []}]}, "non-empty 'calls' list"),
    ({"type": "mock_llm_turns", "turns": [{"calls": [{"result": "res"}]}]}, "a call that is not"),
    ({"type": "ceo_action", "calls": [{"run": ["gh", "pr", "merge", "101"]}]}, "a call that is not {'tool', 'args'}"),
    ({"type": "ceo_action", "input": "YES", "calls": [{"tool": "grant"}]}, "either an 'input'"),
    ({"type": "ceo_action", "input": "MAYBE"}, "either an 'input'"),
])
def test_a_step_the_office_could_not_carry_out_is_refused_by_the_free_checker(step, problem):
    checked = validate_scenario(_scenario([step], includes=["^"]))

    assert not checked.valid
    assert problem in "\n".join(checked.errors)


def test_scenarios_md_shows_the_format_the_validator_accepts_and_where_scenarios_live():
    doc = (ROOT / "docs" / "SCENARIOS.md").read_text()

    examples = re.findall(r"```json\n(.*?)```", doc, re.DOTALL)
    assert len(examples) >= 2  # a single-turn scenario and one with steps
    for example in examples:
        assert validate_scenario(json.loads(example)).errors == []
    named = re.findall(r"`((?:\.claudarama/)?scenarios/[\w./-]*)`", doc)
    assert "scenarios/" in named and ".claudarama/scenarios/" in named
    for path in named:  # the core's own are checked; a pack's are the project's
        assert path.startswith(".claudarama/") or (ROOT / path).exists(), path
