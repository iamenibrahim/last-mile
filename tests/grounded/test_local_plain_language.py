from grounded.providers.local_providers import LocalSimplifier


def test_fallback_preserves_temporal_and_bank_information_meaning():
    simplify = LocalSimplifier().simplify
    assert "following the date" in simplify("The period is 60 days following the date of the declaration.")
    output = simplify("Do not ask for bank information.")
    assert "bank information" in output
    assert "not" in output.lower()
