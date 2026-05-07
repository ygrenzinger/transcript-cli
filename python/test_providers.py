from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from providers import (
    ProviderError,
    get_provider,
    list_providers,
    validate_required_env_vars,
    vertex_gemini_result_to_cues,
)


@dataclass(frozen=True)
class FakeProvider:
    name: str = "fake"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "fake-model"
    required_env_vars: tuple[str, ...] = ("ONE", "TWO")

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"fake-model": "fake-model"})


class ProviderConfigurationTests(unittest.TestCase):
    def test_single_required_env_var_error_names_missing_value(self) -> None:
        provider = FakeProvider(required_env_vars=("ONLY",))

        with self.assertRaisesRegex(ProviderError, "ONLY"):
            validate_required_env_vars(provider, get_env=lambda _: None)

    def test_multiple_required_env_var_error_names_first_missing_value(self) -> None:
        provider = FakeProvider(required_env_vars=("ONE", "TWO"))

        values = {"ONE": "set"}

        with self.assertRaisesRegex(ProviderError, "TWO"):
            validate_required_env_vars(provider, get_env=values.get)


class VertexGeminiProviderTests(unittest.TestCase):
    def test_vertex_gemini_provider_is_registered_and_discoverable(self) -> None:
        provider = get_provider("vertex-gemini")
        payload = json.loads(list_providers())

        self.assertEqual("vertex-gemini", provider.name)
        self.assertEqual("gemini-2.5-flash", provider.default_model)
        self.assertEqual(("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"), provider.required_env_vars)
        self.assertEqual("gemini-2.5-flash", payload["vertex-gemini"]["default_model"])
        self.assertEqual(["gemini-2.5-flash", "gemini-2.5-pro"], payload["vertex-gemini"]["models"])
        self.assertEqual("gemini-2.5-pro", provider.models["gemini-2.5-pro"])

    def test_vertex_gemini_result_to_cues_parses_segments(self) -> None:
        cues = vertex_gemini_result_to_cues(
            {"segments": [{"start": 1.25, "end": 2.5, "text": "Bonjour"}, {"start": 2.5, "end": 4, "text": "le monde"}]}
        )

        self.assertEqual(2, len(cues))
        self.assertEqual(1250, cues[0].start_ms)
        self.assertEqual(2500, cues[0].end_ms)
        self.assertEqual("Bonjour", cues[0].text)
        self.assertEqual(2500, cues[1].start_ms)

    def test_vertex_gemini_result_to_cues_rejects_missing_segments(self) -> None:
        with self.assertRaisesRegex(ProviderError, "no timestamped transcription segments"):
            vertex_gemini_result_to_cues({"segments": []})

    def test_vertex_gemini_result_to_cues_rejects_invalid_timestamp(self) -> None:
        with self.assertRaisesRegex(ProviderError, "invalid start timestamp"):
            vertex_gemini_result_to_cues({"segments": [{"start": "soon", "end": 2, "text": "hello"}]})

    def test_vertex_gemini_result_to_cues_rejects_non_positive_duration(self) -> None:
        with self.assertRaisesRegex(ProviderError, "non-positive-duration"):
            vertex_gemini_result_to_cues({"segments": [{"start": 2, "end": 2, "text": "hello"}]})

    def test_vertex_gemini_result_to_cues_rejects_out_of_order_segments(self) -> None:
        with self.assertRaisesRegex(ProviderError, "out-of-order"):
            vertex_gemini_result_to_cues(
                {"segments": [{"start": 2, "end": 3, "text": "first"}, {"start": 1, "end": 2, "text": "second"}]}
            )


if __name__ == "__main__":
    unittest.main()
