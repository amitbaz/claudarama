"""What a brief contains, and the free check on core role files."""
import pytest

from claudarama.brief import ROLES_DIR, build_brief, check_role_file
from claudarama.db import CAST


def _pack(tmp_path):
    pack = tmp_path / ".claudarama"
    (pack / "profiles").mkdir(parents=True)
    (pack / "company.md").write_text("CHARTER-TEXT\n")
    (pack / "profiles" / "fullstack-engineer.md").write_text("OVERLAY-TEXT\n")
    return pack


def test_a_brief_is_built_in_the_fixed_order(tmp_path):
    brief = build_brief(
        _pack(tmp_path),
        "fullstack-engineer",
        thread=[{"sender": "pm", "receiver": "fullstack-engineer", "msg_type": "START", "body": "THREAD-TEXT"}],
        ticket="TICKET-42",
        working_note="NOTE-TEXT",
        lessons=["LESSON-TEXT"],
    )
    expected_order = [
        "CHARTER-TEXT",
        "# Office rules",
        "You are the fullstack-engineer (Bender).",
        "## What this Role is",
        "OVERLAY-TEXT",
        "LESSON-TEXT",
        "THREAD-TEXT",
        "TICKET-42",
        "NOTE-TEXT",
    ]
    positions = [brief.find(marker) for marker in expected_order]
    assert -1 not in positions, dict(zip(expected_order, positions))
    assert positions == sorted(positions)


# The free check: a core role file has seven fixed parts and 40 to 80 lines.

SEVEN_PARTS = [
    "## What this Role is",
    "## Where it sits in the loop",
    "## What it produces",
    "## Who receives it",
    "## What done is backed by",
    "## What it leaves to others",
    "## When blocked or unclear",
]


def _role_text(parts=SEVEN_PARTS, lines=60):
    body = [line for part in parts for line in (part, "", "Something.", "")]
    return "\n".join(body + ["More."] * (lines - len(body)))


def test_a_role_file_with_seven_parts_and_a_fitting_length_passes():
    assert check_role_file(_role_text()) == []


def test_a_role_file_missing_a_part_fails():
    problems = check_role_file(_role_text(parts=SEVEN_PARTS[:4] + SEVEN_PARTS[5:]))
    assert problems == ["missing part: ## What done is backed by"]


def test_a_role_file_outside_the_length_range_fails():
    assert check_role_file(_role_text(lines=39)) == ["39 lines, outside 40 to 80"]
    assert check_role_file(_role_text(lines=81)) == ["81 lines, outside 40 to 80"]
    assert check_role_file(_role_text(lines=40)) == check_role_file(_role_text(lines=80)) == []


@pytest.mark.parametrize("role", sorted(CAST))
def test_every_role_in_the_cast_has_a_core_role_file(role):
    assert (ROLES_DIR / f"{role}.md").is_file()


@pytest.mark.parametrize("path", sorted(ROLES_DIR.glob("*.md")), ids=lambda path: path.stem)
def test_every_core_role_file_belongs_to_a_role_and_fits_the_template(path):
    assert path.stem in CAST
    assert check_role_file(path.read_text(encoding="utf-8")) == []


# What each brief must tell its reader. Phrases are matched in lower case.

def _missing(brief, phrases):
    return [phrase for phrase in phrases if phrase not in brief.lower()]


@pytest.mark.parametrize("role", ["pm", "designer"])
def test_every_brief_carries_the_shared_office_rules_once(tmp_path, role):
    brief = build_brief(tmp_path, role)
    assert brief.count("# Office rules") == 1
    assert _missing(brief, [
        "## evidence before claims",
        "## stay inside the ticket",
        "## how a turn ends",
        "## when blocked or unclear",
        "post one question",
        "a fix counts only if it beats the measure's spread",
        "too noisy to judge a fix, repairing the measure comes before fixing anything else",
    ]) == []


@pytest.mark.parametrize("role", ["researcher", "eval-engineer"])
def test_an_investigating_roles_brief_requires_a_diagnosis_to_report_spread_and_rivals(tmp_path, role):
    assert _missing(build_brief(tmp_path, role), [
        "the measure the finding relies on",
        "how much it varies across repeated runs of the unchanged system",
        "the code, the prompts, the bars, the tests, the overall approach, and something missing",
        "what was run to check it",
        "not ruled out without evidence",
    ]) == []


@pytest.mark.parametrize("role", [
    "fullstack-engineer", "frontend-engineer", "database-architect",
    "designer", "prompt-engineer", "eval-engineer",
])
def test_a_ticket_roles_brief_hands_one_pull_request_to_the_engineering_lead(tmp_path, role):
    assert _missing(build_brief(tmp_path, role), [
        "one pull request that closes the ticket",
        "the engineering-lead, who is woken when the pull request opens",
        "**bars and expectations**",
        "`question` to the pm",
    ]) == []


def test_the_engineering_leads_brief_ties_ship_to_repeated_runs_and_named_bar_changes(tmp_path):
    assert _missing(build_brief(tmp_path, "engineering-lead"), [
        "a ship verdict rests on repeated runs that beat the spread",
        "every change the pull request makes to a bar, a threshold or a test's expectation",
    ]) == []


def test_the_engineering_leads_brief_says_how_a_retro_submits_its_lessons_and_their_limits(tmp_path):
    assert _missing(build_brief(tmp_path, "engineering-lead"), [
        "pass the lessons to `submit_lessons` as `lessons`",
        "at most three, each a `text` of at most 300 characters and a `scope` of `company` or one role",
        "the office refuses more or longer",
    ]) == []


@pytest.mark.parametrize("role", ["engineering-lead", "eval-engineer"])
def test_a_challenging_roles_brief_names_the_tool_that_records_the_challenge(tmp_path, role):
    assert _missing(build_brief(tmp_path, role), [
        "recorded with `record_challenge`: stands or disputed, with reasons and with what you ran",
    ]) == []


def test_the_assistants_brief_covers_mandates_setup_and_project_knowledge(tmp_path):
    assert _missing(build_brief(tmp_path, "assistant"), [
        # shaping a Mandate and naming the investigator
        "**a mandate**",
        "**investigating role**: researcher by default",
        "call `grant` with the mandate, that ticket and the investigating role",
        # naming the challenger
        "**challenging role**: engineering-lead by default, and never the investigating role",
        "name the eval-engineer when the problem is judged by a test or eval of ai behaviour",
        "tell the ceo both roles before the grant, and pass this one to `grant` as `challenger`",
        # judged cases anchor a quality Mandate
        "this is right, this is wrong, and why",
        "attach them to the mandate",
        "the anchor for what correct means",
        # the setup interview
        "ask a few questions and write the charter",
        "what a newcomer gets wrong, what must never be touched, and what done means beyond passing tests",
        "`## house rules` section of the charter",
        "test commands the repository already defines and propose them to the ceo",
        "agent instructions file",
        "offer to draft one with the ceo",
        # overlays
        "only when it applies to that role alone",
        "do not generate overlays from a scan of the repository",
    ]) == []


def test_the_assistants_brief_covers_reaching_the_ceo_and_answering_gates_in_the_session(tmp_path):
    assert _missing(build_brief(tmp_path, "assistant"), [
        # the watcher wakes the Session when a gate opens, and the Assistant pushes to the phone
        "run `claudarama watch` in the background",
        "send a push with the `pushnotification` tool",
        "start the watcher again",
        # every gate is listed and answered inside the Session, DISCUSS included
        "call `list_gates` and present each gate",
        "pass the ceo's yes or no to `answer_gate`",
        "a no goes with the ceo's one-line reason",
        "discuss is a conversation",
        "until the ceo says yes or no",
        # messages addressed to the CEO are shown together at open
        "**messages for the ceo**",
        "together and in full",
    ]) == []


def test_the_assistants_brief_covers_saving_the_ceos_answer_as_a_lesson_and_removing_one(tmp_path):
    assert _missing(build_brief(tmp_path, "assistant"), [
        # the CEO's answer to a specialist's question about the project
        "offer to save the answer as a lesson, scoped to the company or to that specialist's role",
        "call `adopt_lesson` with the answer as one rule of at most 300 characters",
        # removing a Lesson
        "call `list_lessons`",
        "call `remove_lesson` with its number",
    ]) == []
