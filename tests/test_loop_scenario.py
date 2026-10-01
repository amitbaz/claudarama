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


# The Challenge that opens mandate M's Diagnosis gate, and the engineering-lead's turn that records it.
CHALLENGE_STANDS = {"tool": "record_challenge", "args": {
    "mandate": "M", "verdict": "STANDS", "reasons": "Five runs gave the same spread.", "ran": "the eval, five times"}}
CHALLENGED = {"type": "mock_llm_turns", "turns": [{"role": "engineering-lead", "ticket": "1", "calls": [CHALLENGE_STANDS]}]}


def test_the_loop_scenario_walks_a_mandate_from_its_grant_to_closed():
    result = run_scenario_file(ROOT / "scenarios" / "loop.json")

    assert result.passed, _why(result)


def test_a_ceo_answer_with_no_gate_waiting_fails_the_scenario():
    result = _walk([{"type": "ceo_action", "input": "YES"}], includes=["^"])

    assert not result.passed
    assert "the CEO answered YES, but no gate was waiting" in _why(result)


def test_a_scripted_turn_the_office_did_not_wake_fails_the_scenario():
    unwoken = [{"type": "mock_llm_turns", "turns": [{"ticket": "7", "calls": [{"tool": "whoami"}]}]}]

    result = _walk(unwoken, includes=["^"])

    assert not result.passed
    assert "the office did not wake the researcher on ticket 7" in _why(result)
    assert "researcher calls" not in result.turn_results[0].person_reply


def test_a_turn_that_ends_itself_with_send_still_shows_everything_it_did():
    granted = {"type": "ceo_action", "calls": [{"tool": "grant", "args": {"mandate": "M", "ticket": "1"}}]}
    asks = {"type": "mock_llm_turns", "turns": [{"ticket": "1", "calls": [
        {"tool": "send", "args": {"receiver_id": "pm", "msg_type": "QUESTION", "body": "Which page?", "ticket": "1"}},
        {"run": ["sleep", "0.5"]},
        {"run": ["echo", "still here"]},
    ]}]}

    result = _walk([granted, asks], includes=["researcher runs echo 'still here' -> still here\\nresearcher's turn: done"])

    assert result.passed, _why(result)


def test_a_turn_can_neither_list_nor_answer_a_gate():
    granted = {"type": "ceo_action", "calls": [{"tool": "grant", "args": {"mandate": "M", "ticket": "1"}}]}
    approves_its_own = {"type": "mock_llm_turns", "turns": [{"ticket": "1", "calls": [
        {"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "d.md"}},
        {"tool": "list_gates"},
        {"tool": "answer_gate", "args": {"gate": "diagnosis:M", "answer": "YES"}},
    ]}]}
    # The Challenge opens the gate; the challenger cannot answer it either.
    approves_what_it_challenged = {"type": "mock_llm_turns", "turns": [{"role": "engineering-lead", "ticket": "1", "calls": [
        CHALLENGE_STANDS,
        {"tool": "answer_gate", "args": {"gate": "diagnosis:M", "answer": "YES"}},
    ]}]}

    result = _walk([granted, approves_its_own, approves_what_it_challenged], includes=[
        "researcher calls list_gates .* -> REFUSED: .*owner-only",
        "researcher calls answer_gate .* -> REFUSED: .*owner-only",
        "engineering-lead calls answer_gate .* -> REFUSED: .*owner-only",
        "engineering-lead's turn: done\\nMandate 'M': PLANNING, waiting for the CEO",
    ])

    assert result.passed, _why(result)


# --- a worktree per ticket (issue #91) ---------------------------------------------

M_GRANTED = {"type": "ceo_action", "calls": [{"tool": "grant", "args": {"mandate": "M", "ticket": "1"}}]}
# The researcher opens a pull request from the ticket's branch, withdraws it, and submits a Diagnosis.
# Once it is challenged, the CEO's DISCUSS reviews the gates and wakes nobody on the ticket.
WITHDRAWN_PR = [
    {"run": ["gh", "pr", "create", "--title", "Faster checkout", "--body", "Closes #1"]},
    {"run": ["gh", "pr", "close", "101"]},
    {"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "company/diagnoses/m.md"}},
]
REVIEWED = "CEO answers DISCUSS\\nMandate 'M': PLANNING, waiting for the CEO\\nThe CEO's checkout is on main; worktrees: "


def _on_ticket_1(*calls: dict) -> dict:
    return {"type": "mock_llm_turns", "turns": [{"ticket": "1", "calls": list(calls)}]}


def test_a_closed_pull_request_takes_the_tickets_worktree_and_leaves_its_branch_for_the_next_turn():
    commit = ["git", "-c", "user.name=Amy", "-c", "user.email=amy@example.com", "commit", "--allow-empty", "-m", "Faster checkout"]
    steps = [
        M_GRANTED,
        _on_ticket_1({"run": commit}, *WITHDRAWN_PR),
        CHALLENGED,
        {"type": "ceo_action", "input": "DISCUSS"},
        {"type": "ceo_action", "input": "NO", "reason": "Look at the cart."},
        _on_ticket_1({"run": ["git", "log", "-1", "--format=%s on %D"]}),
    ]

    result = _walk(steps, includes=[
        REVIEWED + "none\\n",
        "researcher runs git log -1 '--format=%s on %D' -> Faster checkout on HEAD -> ticket-1\\nresearcher's turn: done\\n"
        "Mandate 'M': INVESTIGATING\\nThe CEO's checkout is on main; worktrees: ticket-1\\n",
    ])

    assert result.passed, _why(result)


def test_a_worktree_holding_uncommitted_work_stays_when_its_pull_request_closes():
    steps = [
        M_GRANTED, _on_ticket_1({"run": ["touch", "uncommitted-work"]}, *WITHDRAWN_PR), CHALLENGED,
        {"type": "ceo_action", "input": "DISCUSS"},
    ]

    result = _walk(steps, includes=[REVIEWED + "ticket-1\\n"])

    assert result.passed, _why(result)


def test_a_ticket_named_like_a_path_gets_no_worktree_and_its_turn_fails_with_the_reason():
    granted = {"type": "ceo_action", "calls": [{"tool": "grant", "args": {"mandate": "M", "ticket": "../../1"}}]}
    turn = {"type": "mock_llm_turns", "turns": [{"ticket": "../../1", "calls": [{"run": ["pwd"]}]}]}

    result = _walk([granted, turn], includes=[
        "researcher's turn: failed: ValueError: ticket '\\.\\./\\.\\./1' cannot name a worktree\\n"
        "Mandate 'M': INVESTIGATING\\nThe CEO's checkout is on main; worktrees: none\\n",
    ])

    assert result.passed, _why(result)
    assert "researcher runs" not in result.turn_results[0].person_reply


def test_the_grant_names_who_investigates_and_a_no_goes_back_to_them():
    steps = [
        {"type": "ceo_action", "calls": [
            {"tool": "grant", "args": {"mandate": "M", "ticket": "1", "investigator": "eval-engineer"}},
            {"tool": "grant", "args": {"mandate": "M", "ticket": "1", "investigator": "eval-engineer"}},
            {"tool": "grant", "args": {"mandate": "N", "ticket": "2", "investigator": "detective"}},
        ]},
        {"type": "mock_llm_turns", "turns": [{"role": "eval-engineer", "ticket": "1", "calls": [
            {"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "company/diagnoses/m.md"}},
        ]}]},
        CHALLENGED,
        {"type": "ceo_action", "input": "NO", "reason": "The eval is too noisy to tell."},
    ]

    result = _walk(steps, includes=[
        # Granting twice wakes the investigating Role once; a Role the office does not have is refused.
        "REFUSED: .*unknown Role 'detective'.*\\neval-engineer is woken on ticket 1\\nMandate 'M': INVESTIGATING\\n",
        # A submitted Diagnosis wakes the challenging Role; the gate opens once the Challenge is recorded.
        "eval-engineer's turn: done\\nengineering-lead is woken on ticket 1\\nMandate 'M': INVESTIGATING\\n",
        "engineering-lead calls record_challenge .* -> \\{\"ok\": true.*\\n"
        "engineering-lead's turn: done\\nMandate 'M': PLANNING, waiting for the CEO\\n",
        "CEO's reason: The eval is too noisy to tell\\.\\neval-engineer is woken on ticket 1\\nMandate 'M': INVESTIGATING\\nThe CEO's checkout .*\\n$",
    ])

    assert result.passed, _why(result)
    assert "Mandate 'N'" not in result.turn_results[0].person_reply


def test_the_grant_names_a_challenging_role_that_is_not_the_investigating_role():
    def grant(mandate, ticket, **roles):
        return {"tool": "grant", "args": {"mandate": mandate, "ticket": ticket, **roles}}

    result = _walk([{"type": "ceo_action", "calls": [
        grant("M", "1", investigator="eval-engineer", challenger="eval-engineer"),
        grant("M", "1", investigator="engineering-lead"),  # the default challenger is the engineering-lead
        grant("M", "1", challenger="detective"),
        grant("M", "1", investigator="eval-engineer", challenger="researcher"),
        grant("N", "2"),
    ]}], includes=[
        "REFUSED: .*challenging Role must differ from the investigating Role.*\\n"
        "CEO calls .* -> REFUSED: .*challenging Role must differ.*\\n"
        "CEO calls .* -> REFUSED: .*unknown Role 'detective'.*\\n"
        "CEO calls .* -> \\{\"ok\": true.*\"investigator\": \"eval-engineer\", \"challenger\": \"researcher\"\\}\\n"
        "CEO calls .* -> \\{\"ok\": true.*\"investigator\": \"researcher\", \"challenger\": \"engineering-lead\"\\}\\n"
        "eval-engineer is woken on ticket 1\\nresearcher is woken on ticket 2\\n",
    ])

    assert result.passed, _why(result)


# --- the loop moves itself: execute and learn (issue #90) ----------------------------


def test_a_mandate_moves_to_learning_when_a_turn_closes_its_last_ticket():
    steps = [
        M_GRANTED,
        _on_ticket_1({"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "company/diagnoses/m.md"}}),
        CHALLENGED,
        {"type": "ceo_action", "input": "YES"},
        {"type": "mock_llm_turns", "turns": [{"role": "pm", "ticket": "1", "calls": [
            {"run": ["gh", "issue", "close", "1"]},
            {"tool": "submit_epic", "args": {"mandate": "M", "tickets": {"2": "designer"}}},
        ]}]},
        {"type": "ceo_action", "input": "YES"},
        {"type": "mock_llm_turns", "turns": [{"role": "designer", "ticket": "2", "calls": [{"run": ["gh", "issue", "close", "2"]}]}]},
    ]

    result = _walk(steps, includes=[
        # No CEO answer moved it: the office saw the last ticket closed when the turn ended.
        "designer's turn: done\\nengineering-lead is woken on ticket 1\\nMandate 'M': LEARNING\\n",
    ])

    assert result.passed, _why(result)


# --- a per-mandate report of where the office went wrong (issue #97) -----------------

STATUS = {"type": "ceo_action", "command": "status"}  # the CEO runs `claudarama status`
TURN = "done, 100 in, 20 out, \\$0\\.01, transcript: /.+/turns/[0-9a-f-]{36}\\.jsonl\\n"  # the stand-in's usage


def test_status_shows_for_a_mandate_each_role_with_its_turns_in_order_its_usage_and_each_transcript():
    steps = [
        M_GRANTED,
        _on_ticket_1({"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "company/diagnoses/m.md"}}),
        CHALLENGED,
        {"type": "ceo_action", "input": "NO", "reason": "Look at the cart."},
        _on_ticket_1({"tool": "whoami"}),
        STATUS,
    ]

    result = _walk(steps, includes=[
        "CEO runs claudarama status\\n",
        "\\n--- Mandate 'M': INVESTIGATING ---\\n"
        "researcher \\(Amy\\): 2 turns, 200 in, 40 out, \\$0\\.02\\n"
        f"  turn 1 on ticket 1: {TURN}"
        f"  turn 3 on ticket 1: {TURN}"
        "engineering-lead \\(Kif\\): 1 turn, 100 in, 20 out, \\$0\\.01\\n"
        f"  turn 2 on ticket 1: {TURN}",
    ])

    assert result.passed, _why(result)


def test_status_shows_each_question_and_blocked_message_a_role_sent():
    def sends(receiver, msg_type, body):
        return {"tool": "send", "args": {"receiver_id": receiver, "msg_type": msg_type, "body": body, "ticket": "1"}}

    steps = [
        M_GRANTED,
        _on_ticket_1(
            {"tool": "submit_diagnosis", "args": {"mandate": "M", "diagnosis_path": "company/diagnoses/m.md"}},
            sends("pm", "QUESTION", "Which page?"),
        ),
        {"type": "mock_llm_turns", "turns": [
            {"role": "engineering-lead", "ticket": "1", "calls": [sends("ceo", "BLOCKED", "The eval will not run here.")]},
        ]},
        STATUS,
    ]

    result = _walk(steps, includes=[
        # The pm's turn waits out the batch window: a turn that has not started has no transcript.
        "pm \\(Hermes\\): 1 turn, 0 in, 0 out, \\$0\\.00\\n  turn 3 on ticket 1: queued, 0 in, 0 out, \\$0\\.00, no transcript\\n"
        "QUESTION from researcher \\(Amy\\) to pm \\(Hermes\\) on ticket 1: Which page\\?\\n"
        "BLOCKED from engineering-lead \\(Kif\\) to ceo on ticket 1: The eval will not run here\\.\\n",
    ])

    assert result.passed, _why(result)


def test_status_shows_a_failed_turn_with_its_error():
    granted = {"type": "ceo_action", "calls": [{"tool": "grant", "args": {"mandate": "M", "ticket": "../../1"}}]}
    turn = {"type": "mock_llm_turns", "turns": [{"ticket": "../../1", "calls": [{"run": ["pwd"]}]}]}

    result = _walk([granted, turn, STATUS], includes=[
        "researcher \\(Amy\\): 1 turn, 0 in, 0 out, \\$0\\.00\\n  turn 1 on ticket \\.\\./\\.\\./1: "
        "failed: ValueError: ticket '\\.\\./\\.\\./1' cannot name a worktree, 0 in, 0 out, \\$0\\.00, no transcript\\n",
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
    ({"type": "ceo_action", "input": "NO"}, "a one-line 'reason' with NO"),
    ({"type": "ceo_action", "input": "NO", "reason": "Wrong page.\nAnd too slow."}, "a one-line 'reason' with NO"),
    ({"type": "ceo_action", "input": "YES", "reason": "Looks right."}, "only with NO"),
    ({"type": "ceo_action", "command": "open"}, "only the 'command' status"),
    ({"type": "ceo_action", "command": "status", "input": "YES"}, "only the 'command' status"),
])
def test_a_step_the_office_could_not_carry_out_is_refused_by_the_free_checker(step, problem):
    checked = validate_scenario(_scenario([step], includes=["^"]))

    assert not checked.valid
    assert problem in "\n".join(checked.errors)


def test_company_md_names_who_the_office_wakes_at_each_transition():
    rows = dict(re.findall(r"^\| (.+?) \| (.+?) \|$", (ROOT / "docs" / "COMPANY.md").read_text(), re.MULTILINE))

    for event, woken in [
        ("Mandate granted", "The investigating Role"),
        ("Diagnosis submitted", "The challenging Role"),
        ("Challenge DISPUTED, first on a Mandate", "The investigating Role, with the reasons"),
        ("Diagnosis gate YES", "The pm"),
        ("Epic gate YES", "Each ticket's Role"),
        ("A Pull Request opens for a ticket, or takes a new push", "The engineering-lead"),
        ("Ship-check FAIL, first on a ticket", "The ticket's Role, with the reason"),
        ("Ship-check FAIL, second on a ticket", "The investigating Role, with both reasons"),
        ("Every ticket of the Mandate closed", "The engineering-lead, to write the Retro"),
        ("Any Gate NO", "Whoever produced the work, with the CEO's reason"),
    ]:
        assert rows.get(event, "").startswith(woken), event


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
