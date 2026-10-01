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


def test_the_five_roles_the_loop_cannot_run_without_have_core_role_files():
    loop_roles = {"assistant", "researcher", "pm", "engineering-lead", "fullstack-engineer"}
    assert loop_roles <= {path.stem for path in ROLES_DIR.glob("*.md")}


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
    if not (ROLES_DIR / f"{role}.md").is_file():
        pytest.skip(f"no core role file for {role} yet")
    assert _missing(build_brief(tmp_path, role), [
        "the measure the finding relies on",
        "how much it varies across repeated runs of the unchanged system",
        "the code, the prompts, the bars, the tests, the overall approach, and something missing",
        "what was run to check it",
        "not ruled out without evidence",
    ]) == []


def test_the_engineering_leads_brief_ties_ship_to_repeated_runs_and_named_bar_changes(tmp_path):
    assert _missing(build_brief(tmp_path, "engineering-lead"), [
        "a ship verdict rests on repeated runs that beat the spread",
        "every change the pull request makes to a bar, a threshold or a test's expectation",
    ]) == []


def test_the_assistants_brief_covers_mandates_setup_and_project_knowledge(tmp_path):
    assert _missing(build_brief(tmp_path, "assistant"), [
        # shaping a Mandate and naming the investigator
        "**a mandate**",
        "**investigating role**: researcher by default",
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
