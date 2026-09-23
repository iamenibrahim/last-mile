from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Secrets are read from the environment and never logged."""

    app_name: str = "Last-Mile Navigator"
    environment: str = os.getenv("APP_ENV", "local")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    nws_user_agent: str = os.getenv(
        "NWS_USER_AGENT", "LastMileNavigator/1.0 (innovation-demo@example.org)"
    )
    manifest_signing_key: str = os.getenv(
        "MANIFEST_SIGNING_KEY", "local-demo-key-not-for-production"
    )
    foundry_endpoint: str = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
    foundry_api_key: str = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    foundry_model: str = os.getenv("AZURE_FOUNDRY_MODEL", "gpt-4.1-mini")
    use_managed_identity: bool = os.getenv("AZURE_USE_MANAGED_IDENTITY", "false").lower() == "true"
    translator_endpoint: str = os.getenv(
        "AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com"
    ).rstrip("/")
    translator_key: str = os.getenv("AZURE_TRANSLATOR_KEY", "")
    translator_region: str = os.getenv("AZURE_TRANSLATOR_REGION", "")
    speech_key: str = os.getenv("AZURE_SPEECH_KEY", "")
    speech_region: str = os.getenv("AZURE_SPEECH_REGION", "")
    content_safety_endpoint: str = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "").rstrip("/")
    content_safety_key: str = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")
    azure_maps_key: str = os.getenv("AZURE_MAPS_KEY", "")
    cosmos_endpoint: str = os.getenv("AZURE_COSMOS_ENDPOINT", "")
    communication_endpoint: str = os.getenv("AZURE_COMMUNICATION_ENDPOINT", "").rstrip("/")
    communication_connection_string: str = os.getenv(
        "AZURE_COMMUNICATION_CONNECTION_STRING", ""
    )
    sms_from_number: str = os.getenv("AZURE_SMS_FROM_NUMBER", "")
    sms_send_enabled: bool = os.getenv("SMS_SEND_ENABLED", "false").lower() == "true"
    sms_auto_reply_enabled: bool = os.getenv("SMS_AUTOREPLY_ENABLED", "false").lower() == "true"
    sms_allowed_test_recipients: tuple[str, ...] = tuple(
        number.strip()
        for number in os.getenv("SMS_ALLOWED_TEST_RECIPIENTS", "").split(",")
        if number.strip()
    )
    call_from_number: str = os.getenv("AZURE_CALL_FROM_NUMBER", "")
    call_start_enabled: bool = os.getenv("CALL_START_ENABLED", "false").lower() == "true"
    call_allowed_test_recipients: tuple[str, ...] = tuple(
        number.strip()
        for number in os.getenv("CALL_ALLOWED_TEST_RECIPIENTS", "").split(",")
        if number.strip()
    )
    call_cognitive_endpoint: str = os.getenv("AZURE_CALL_COGNITIVE_ENDPOINT", "").rstrip("/")
    call_voice_name: str = os.getenv("AZURE_CALL_VOICE_NAME", "en-US-JennyNeural")
    call_source_locale: str = os.getenv("AZURE_CALL_SOURCE_LOCALE", "en-US")

    @property
    def foundry_enabled(self) -> bool:
        return bool(self.foundry_endpoint and (self.foundry_api_key or self.use_managed_identity))

    @property
    def translator_enabled(self) -> bool:
        return bool(self.translator_key)

    @property
    def speech_enabled(self) -> bool:
        return bool(self.speech_key and self.speech_region)

    @property
    def content_safety_enabled(self) -> bool:
        return bool(self.content_safety_endpoint and self.content_safety_key)

    @property
    def sms_enabled(self) -> bool:
        has_auth = bool(self.communication_connection_string or self.communication_endpoint)
        return bool(self.sms_send_enabled and has_auth and self.sms_from_number)

    @property
    def call_enabled(self) -> bool:
        has_auth = bool(self.communication_connection_string or self.communication_endpoint)
        callback_is_public = self.public_base_url.startswith("https://")
        return bool(
            self.call_start_enabled
            and has_auth
            and self.call_from_number
            and self.call_cognitive_endpoint
            and callback_is_public
        )


settings = Settings()
