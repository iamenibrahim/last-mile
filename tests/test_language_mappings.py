from api.providers.azure_translator import service_language
from api.speech import VOICES


def test_challenge_languages_map_to_microsoft_service_codes():
    assert service_language("es") == "es"
    assert service_language("ar") == "ar"
    assert service_language("prs") == "prs"
    assert service_language("tl") == "fil"


def test_challenge_languages_have_azure_neural_voices():
    assert set(("es", "ar", "prs", "tl")) <= VOICES.keys()
    assert all(VOICES[lang].endswith("Neural") for lang in ("es", "ar", "prs", "tl"))
