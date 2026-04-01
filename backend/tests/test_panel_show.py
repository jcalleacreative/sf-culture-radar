# backend/tests/test_panel_show.py

from unittest.mock import patch

from llm.panel_show import _validate_candidate, generate_panel_show, validate_input_stories

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

STORY_NO_IMAGE = {
    "id": "s1",
    "headline": "SF cafe charges $18 for avocado toast",
    "source": "SFGATE",
    "url": "https://example.com/s1",
}

STORY_WITH_IMAGE = {
    "id": "s2",
    "headline": "Wolf spotted swimming toward Alcatraz",
    "source": "SF Standard",
    "url": "https://example.com/s2",
    "image_url": "https://example.com/wolf.jpg",
}

STORY_INDEX = {
    "s1": STORY_NO_IMAGE,
    "s2": STORY_WITH_IMAGE,
}


def _base_seg(overrides=None):
    """Return a minimal valid 'scenes' segment dict."""
    seg = {
        "type": "scenes",
        "story_id": "s1",
        "prompt": "Things the barista says when you question the price",
        "host_intro": "Next up, Scenes We'd Like to See.",
        "panelist_task": "Give one-line scene responses.",
        "speed": "fast",
        "fit_score": 8,
        "reason_short": "absurd local price",
    }
    if overrides:
        seg.update(overrides)
    return seg


# ---------------------------------------------------------------------------
# validate_input_stories
# ---------------------------------------------------------------------------

def test_validate_input_stories_valid():
    errors = validate_input_stories([STORY_NO_IMAGE, STORY_WITH_IMAGE])
    assert errors == []


def test_validate_input_stories_missing_fields():
    bad = {"id": "x", "headline": "Missing source and url"}
    errors = validate_input_stories([bad])
    assert len(errors) == 1
    assert "source" in errors[0]["detail"] or "url" in errors[0]["detail"]


def test_validate_input_stories_non_dict():
    errors = validate_input_stories(["not a dict"])
    assert len(errors) == 1
    assert "not a JSON object" in errors[0]["detail"]


# ---------------------------------------------------------------------------
# _validate_candidate — base cases
# ---------------------------------------------------------------------------

def test_valid_scenes_candidate():
    result, reason = _validate_candidate(_base_seg(), STORY_INDEX)
    assert reason is None
    assert result is not None
    assert result["headline"] == STORY_NO_IMAGE["headline"]
    assert result["display_label"] == "Scenes We'd Like to See"


def test_missing_required_field_dropped():
    seg = _base_seg()
    del seg["prompt"]
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "prompt" in reason


def test_prompt_too_long_dropped():
    seg = _base_seg({"prompt": "x" * 151})
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "too long" in reason


def test_speed_normalized_when_invalid():
    seg = _base_seg({"speed": "turbo"})
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is not None
    assert result["speed"] == "medium"


def test_fit_score_clamped():
    seg = _base_seg({"fit_score": 99})
    result, _ = _validate_candidate(seg, STORY_INDEX)
    assert result["fit_score"] == 10

    seg = _base_seg({"fit_score": -5})
    result, _ = _validate_candidate(seg, STORY_INDEX)
    assert result["fit_score"] == 1


# ---------------------------------------------------------------------------
# _validate_candidate — unknown story_id
# ---------------------------------------------------------------------------

def test_unknown_story_id_dropped():
    seg = _base_seg({"story_id": "s999"})
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "s999" in reason


# ---------------------------------------------------------------------------
# _validate_candidate — if_this_is_the_answer
# ---------------------------------------------------------------------------

def test_valid_if_this_is_the_answer():
    seg = {
        "type": "if_this_is_the_answer",
        "story_id": "s1",
        "prompt": "What does it cost to feel judged in SF?",
        "host_intro": "The answer is...",
        "panelist_task": "Buzz in with a question.",
        "speed": "medium",
        "fit_score": 9,
        "reason_short": "concrete absurd price",
        "answer": "$18",
        "reveal": "A Mission cafe charged $18 for avocado toast",
    }
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert reason is None
    assert result["answer"] == "$18"
    assert result["reveal"] == "A Mission cafe charged $18 for avocado toast"
    assert "candidate_id" not in result  # assigned later by generate_panel_show


def test_if_this_is_the_answer_missing_answer_dropped():
    seg = {
        "type": "if_this_is_the_answer",
        "story_id": "s1",
        "prompt": "What does it cost?",
        "host_intro": "The answer is...",
        "panelist_task": "Buzz in.",
        "speed": "medium",
        "reveal": "some reveal",
        # "answer" is intentionally missing
    }
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "answer" in reason


# ---------------------------------------------------------------------------
# _validate_candidate — picture_of_week
# ---------------------------------------------------------------------------

def test_picture_of_week_valid_when_image_present():
    seg = {
        "type": "picture_of_week",
        "story_id": "s2",
        "prompt": "Caption this photo of the Alcatraz wolf",
        "host_intro": "Picture of the Week.",
        "panelist_task": "React or caption the image.",
        "speed": "medium",
        "fit_score": 7,
        "reason_short": "highly visual local story",
    }
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert reason is None
    assert result["image_url"] == "https://example.com/wolf.jpg"


def test_picture_of_week_dropped_without_image():
    seg = {
        "type": "picture_of_week",
        "story_id": "s1",  # STORY_NO_IMAGE has no image_url
        "prompt": "Caption this photo",
        "host_intro": "Picture of the Week.",
        "panelist_task": "React to the image.",
        "speed": "medium",
        "fit_score": 6,
        "reason_short": "imageable story",
    }
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "image_url" in reason


def test_picture_of_week_image_hydrated_from_source_not_model():
    """Model-supplied image_url should be overwritten by source story value."""
    seg = {
        "type": "picture_of_week",
        "story_id": "s2",
        "prompt": "Caption this",
        "host_intro": "Picture of the Week.",
        "panelist_task": "React.",
        "speed": "medium",
        "image_url": "https://evil.com/injected.jpg",  # model hallucinated URL
    }
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert reason is None
    assert result["image_url"] == "https://example.com/wolf.jpg"  # source wins


# ---------------------------------------------------------------------------
# _validate_candidate — unlikely_things / wildcard
# ---------------------------------------------------------------------------

def test_unlikely_things_missing_target_dropped():
    seg = _base_seg({"type": "unlikely_things"})  # no "target"
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "target" in reason


def test_wildcard_invalid_mode_dropped():
    seg = _base_seg({"type": "wildcard", "wildcard_mode": "anything_goes"})
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert result is None
    assert "wildcard_mode" in reason


def test_wildcard_valid_mode_accepted():
    seg = _base_seg({
        "type": "wildcard",
        "wildcard_mode": "bad_startup_pitch",
        "prompt": "Pitch me $18 toast as a startup",
    })
    result, reason = _validate_candidate(seg, STORY_INDEX)
    assert reason is None
    assert result["wildcard_mode"] == "bad_startup_pitch"


# ---------------------------------------------------------------------------
# generate_panel_show — grouped output shape
# ---------------------------------------------------------------------------

def test_grouped_output_shape():
    stories = [STORY_NO_IMAGE, STORY_WITH_IMAGE]

    mock_llm_response = {
        "segments": [
            {
                "type": "scenes",
                "story_id": "s1",
                "prompt": "Things the barista says defending the price",
                "host_intro": "Scenes We'd Like to See.",
                "panelist_task": "One-liner each.",
                "speed": "fast",
                "fit_score": 8,
                "reason_short": "local absurdity",
            },
            {
                "type": "picture_of_week",
                "story_id": "s2",
                "prompt": "Caption this wolf selfie",
                "host_intro": "Picture of the Week.",
                "panelist_task": "React or caption.",
                "speed": "medium",
                "fit_score": 9,
                "reason_short": "strong visual hook",
            },
        ],
        "unused_stories": [
            {"story_id": "s1", "reason": "used in scenes already"},
        ],
    }

    with patch("llm.panel_show._call_llm", return_value=mock_llm_response):
        result = generate_panel_show(stories)

    assert "segments" in result
    assert "unused_stories" in result
    assert isinstance(result["segments"], dict)

    assert "scenes" in result["segments"]
    scenes = result["segments"]["scenes"]
    assert len(scenes) == 1
    assert scenes[0]["headline"] == STORY_NO_IMAGE["headline"]  # hydrated
    assert scenes[0]["display_label"] == "Scenes We'd Like to See"
    assert scenes[0]["candidate_id"].startswith("scenes_s1_")

    assert "picture_of_week" in result["segments"]
    pic = result["segments"]["picture_of_week"][0]
    assert pic["image_url"] == "https://example.com/wolf.jpg"  # hydrated from source


def test_invalid_segments_dropped_from_output():
    """Segments with bad story_ids should be silently dropped."""
    stories = [STORY_NO_IMAGE]

    mock_llm_response = {
        "segments": [
            {   # valid
                "type": "scenes",
                "story_id": "s1",
                "prompt": "Things the barista says",
                "host_intro": "Scenes We'd Like to See.",
                "panelist_task": "One-liner.",
                "speed": "fast",
            },
            {   # invalid — story_id not in input
                "type": "scenes",
                "story_id": "ghost-story",
                "prompt": "This should be dropped",
                "host_intro": "...",
                "panelist_task": "...",
                "speed": "fast",
            },
        ],
        "unused_stories": [],
    }

    with patch("llm.panel_show._call_llm", return_value=mock_llm_response):
        result = generate_panel_show(stories)

    assert len(result["segments"].get("scenes", [])) == 1
    assert result["segments"]["scenes"][0]["story_id"] == "s1"
