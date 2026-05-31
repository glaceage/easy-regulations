from apps.api.models.revision import RevisionState, can_transition


def test_draft_to_in_consultation():
    assert can_transition(RevisionState.DRAFT, RevisionState.IN_CONSULTATION) is True


def test_draft_to_published_blocked():
    assert can_transition(RevisionState.DRAFT, RevisionState.PUBLISHED) is False


def test_in_consultation_to_in_revision():
    assert can_transition(RevisionState.IN_CONSULTATION, RevisionState.IN_REVISION) is True


def test_pending_publish_to_published_blocked():
    assert can_transition(RevisionState.PENDING_PUBLISH, RevisionState.PUBLISHED) is False
