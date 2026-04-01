"""Tests for LLM client."""

from unittest.mock import MagicMock, patch

from lmetl.llm.client import LLMClient, ExtractionResponse


class TestLLMClient:
    def test_init_from_config(self):
        with patch("lmetl.llm.client.openai.OpenAI"):
            config = {
                "endpoint": "http://localhost:11434",
                "model": "test-model",
                "timeout": 120,
                "max_retries": 2,
                "parameters": {"temperature": 0.5, "top_k": 30},
            }
            client = LLMClient(config)
            assert client.model == "test-model"
            assert client.endpoint == "http://localhost:11434"
            assert client.timeout == 120
            assert client.parameters["temperature"] == 0.5
            assert client.parameters["top_k"] == 30

    def test_init_defaults(self):
        with patch("lmetl.llm.client.openai.OpenAI"):
            client = LLMClient({})
            assert client.model == "gpt-oss:120b"
            assert client.endpoint == "http://192.168.9.160:11434"
            assert client.parameters == {}

    def test_extract_returns_response(self):
        with patch("lmetl.llm.client.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 100
            mock_usage.completion_tokens = 50

            mock_choice = MagicMock()
            mock_choice.message.content = '{"title": "test"}'

            mock_response = MagicMock()
            mock_response.usage = mock_usage
            mock_response.choices = [mock_choice]

            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient({"parameters": {"temperature": 0.1}})
            result = client.extract("system", "user")

            assert isinstance(result, ExtractionResponse)
            assert result.content == '{"title": "test"}'
            assert result.token_usage_input == 100
            assert result.token_usage_output == 50
            assert result.latency_ms >= 0

    def test_extract_passes_parameters(self):
        with patch("lmetl.llm.client.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 10
            mock_usage.completion_tokens = 5

            mock_choice = MagicMock()
            mock_choice.message.content = "{}"

            mock_response = MagicMock()
            mock_response.usage = mock_usage
            mock_response.choices = [mock_choice]

            mock_client.chat.completions.create.return_value = mock_response

            config = {
                "parameters": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "top_k": 40,
                    "min_p": 0.05,
                    "num_predict": 4096,
                },
            }
            client = LLMClient(config)
            client.extract("system", "user")

            call_kwargs = mock_client.chat.completions.create.call_args
            # temperature and top_p are direct params
            assert call_kwargs.kwargs.get("temperature") == 0.2
            assert call_kwargs.kwargs.get("top_p") == 0.9
            # top_k, min_p, num_predict go via extra_body
            extra = call_kwargs.kwargs.get("extra_body", {})
            assert extra.get("top_k") == 40
            assert extra.get("min_p") == 0.05
            assert extra.get("num_predict") == 4096
