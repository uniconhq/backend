"""PKCE, against the worked example in RFC 7636."""

from unicon.auth.pkce import challenge_for, new_verifier

RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_the_challenge_matches_the_specification() -> None:
    assert challenge_for(RFC_VERIFIER) == RFC_CHALLENGE


def test_verifiers_are_fresh_and_long_enough() -> None:
    verifier = new_verifier()

    assert 43 <= len(verifier) <= 128
    assert verifier != new_verifier()
