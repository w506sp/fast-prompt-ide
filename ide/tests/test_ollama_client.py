import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase, override_settings

from ide import ollama_client


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _resp(payload):
    return _FakeResp(json.dumps(payload).encode("utf-8"))


@override_settings(OLLAMA_BASE_URL="http://example:11434")
class OllamaClientTests(SimpleTestCase):
    def test_list_models_returns_names(self):
        with patch("ide.ollama_client.urllib.request.urlopen") as mock_open:
            mock_open.return_value = _resp({"models": [{"name": "llama3"}, {"name": "mistral"}]})
            self.assertEqual(ollama_client.list_models(), ["llama3", "mistral"])
        called_url = mock_open.call_args.args[0].full_url
        self.assertEqual(called_url, "http://example:11434/api/tags")

    def test_list_models_empty_on_unreachable(self):
        with patch("ide.ollama_client.urllib.request.urlopen", side_effect=URLError("nope")):
            self.assertEqual(ollama_client.list_models(), [])

    def test_generate_posts_payload_and_returns_dict(self):
        with patch("ide.ollama_client.urllib.request.urlopen") as mock_open:
            mock_open.return_value = _resp({"response": "hi", "eval_count": 3})
            out = ollama_client.generate("llama3", "say hi", options={"temperature": 0.1})

        self.assertEqual(out["response"], "hi")
        request = mock_open.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, "http://example:11434/api/generate")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "llama3")
        self.assertEqual(body["prompt"], "say hi")
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"], {"temperature": 0.1})

    def test_generate_raises_ollama_error_on_url_error(self):
        with patch("ide.ollama_client.urllib.request.urlopen", side_effect=URLError("down")):
            with self.assertRaisesRegex(ollama_client.OllamaError, "Could not reach"):
                ollama_client.generate("llama3", "hi")

    def test_generate_surfaces_http_error_body(self):
        http_err = HTTPError(
            url="http://example:11434/api/generate",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"model not found"}'),
        )
        with patch("ide.ollama_client.urllib.request.urlopen", side_effect=http_err):
            with self.assertRaisesRegex(ollama_client.OllamaError, "HTTP 404"):
                ollama_client.generate("nope", "hi")
