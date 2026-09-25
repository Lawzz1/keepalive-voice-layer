import pytest

from safety_gate import CLOSING, FALLBACK_ACTIVE, FALLBACK_AFTER, MAX_WORDS_ACTIVE, gate


@pytest.mark.parametrize("text", [
    "You can stop compressions now.",
    "If he wakes up, stop pushing.",
    "Take a short rest from CPR.",
    "Check his pulse first.",
    "Give him some water.",
    "An aspirin might help.",
])
def test_active_rules_replace(text):
    r = gate(text, "active")
    assert r.action == "replaced"
    assert r.text == FALLBACK_ACTIVE


@pytest.mark.parametrize("text, reason", [
    ("Give 0.3 mg of epinephrine.", "dose"),
    ("Inject 5 ml now.", "dose"),
    ("I'm so sorry, he's dead.", "death"),
    ("She can't be saved.", "death"),
    ("You don't need to call anyone.", "dont_call"),
    ("Do not call the ambulance yet.", "dont_call"),
])
@pytest.mark.parametrize("state", ["active", "handoff"])
def test_always_rules_replace_in_every_state(text, reason, state):
    r = gate(text, state)
    assert (r.action, r.reason) == ("replaced", reason)


def test_dont_stop_is_allowed():
    r = gate("Don't stop pushing, you are doing great.", "active")
    assert r.action == "closing_added"
    assert r.text.endswith(CLOSING)


def test_closing_added_and_short():
    r = gate("No, nothing by mouth.", "active")
    assert r.text == f"No, nothing by mouth. {CLOSING}"
    assert len(r.text.split()) <= MAX_WORDS_ACTIVE


def test_closing_already_there():
    assert gate(CLOSING, "active").action == "passed"


def test_too_long_is_replaced():
    long = "Hands only CPR is completely fine if you have never been trained and you are alone with him right now"
    r = gate(long, "active")
    assert (r.action, r.reason) == ("replaced", "too_long")


def test_empty_is_replaced():
    assert gate("   ", "active").text == FALLBACK_ACTIVE
    assert gate("", "handoff").text == FALLBACK_AFTER


def test_after_the_emergency_allows_water_and_trims():
    assert gate("Drink some water and sit down.", "handoff").action == "passed"
    r = gate("You did well. Breathe in. Breathe out. They will take him to hospital. Call family.", "handoff")
    assert r.action == "trimmed"
    assert r.text == "You did well. Breathe in. Breathe out."


def test_after_the_emergency_has_no_closing():
    r = gate("The paramedics will keep him stable.", "handoff")
    assert not r.text.endswith(CLOSING)


def test_briefing_keeps_the_whole_ems_report():
    """The handover report is machine-built from the log: trimming it loses facts."""
    report = ("EMS Handoff: ADULT patient with Cardiac Arrest. Bystander CPR performed "
              "for 50 seconds, approximately 92 compressions delivered at 110 BPM. "
              "Initial presentation included agonal gasping. Public access AED was deployed.")
    result = gate(report, "briefing")
    assert result.action == "passed"
    assert result.text == report
    assert "AED was deployed" in result.text


def test_briefing_still_blocks_a_dose():
    result = gate("Give him 0.3 mg of epinephrine on arrival.", "briefing")
    assert (result.action, result.reason) == ("replaced", "dose")


def test_briefing_never_appends_the_cpr_closing():
    result = gate("Patient handed over to Medic-4.", "briefing")
    assert CLOSING not in result.text
