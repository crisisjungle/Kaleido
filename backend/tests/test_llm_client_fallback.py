import unittest

from app.config import Config
from app.utils import llm_client as llm_module


class _FakeCompletionAPI:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.calls.append(kwargs)
        if self.parent.should_fail:
            raise RuntimeError(f"{self.parent.label} quota exceeded")
        return type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": self.parent.content})()},
                    )()
                ]
            },
        )()


class _FakeOpenAI:
    instances = []
    planned = []

    def __init__(self, api_key, base_url):
        config = self.planned.pop(0)
        self.api_key = api_key
        self.base_url = base_url
        self.label = config["label"]
        self.should_fail = config["should_fail"]
        self.content = config["content"]
        self.calls = []
        self.chat = type("ChatAPI", (), {"completions": _FakeCompletionAPI(self)})()
        self.__class__.instances.append(self)


class LLMClientFallbackTestCase(unittest.TestCase):
    def setUp(self):
        self.orig_openai = llm_module.OpenAI
        self.orig_api_key = Config.LLM_API_KEY
        self.orig_base_url = Config.LLM_BASE_URL
        self.orig_model = Config.LLM_MODEL_NAME
        self.orig_fallback_api_key = Config.LLM_FALLBACK_API_KEY
        self.orig_fallback_base_url = Config.LLM_FALLBACK_BASE_URL
        self.orig_fallback_model = Config.LLM_FALLBACK_MODEL_NAME
        self.orig_thinking = Config.DEEPSEEK_THINKING_MODE
        self.orig_effort = Config.DEEPSEEK_REASONING_EFFORT

        llm_module.OpenAI = _FakeOpenAI
        _FakeOpenAI.instances = []
        _FakeOpenAI.planned = []

        Config.LLM_API_KEY = "primary-key"
        Config.LLM_BASE_URL = "https://api.primary.example/v1"
        Config.LLM_MODEL_NAME = "primary-model"
        Config.LLM_FALLBACK_API_KEY = None
        Config.LLM_FALLBACK_BASE_URL = Config.LLM_BASE_URL
        Config.LLM_FALLBACK_MODEL_NAME = Config.LLM_MODEL_NAME
        Config.DEEPSEEK_THINKING_MODE = "auto"
        Config.DEEPSEEK_REASONING_EFFORT = "high"

    def tearDown(self):
        llm_module.OpenAI = self.orig_openai
        Config.LLM_API_KEY = self.orig_api_key
        Config.LLM_BASE_URL = self.orig_base_url
        Config.LLM_MODEL_NAME = self.orig_model
        Config.LLM_FALLBACK_API_KEY = self.orig_fallback_api_key
        Config.LLM_FALLBACK_BASE_URL = self.orig_fallback_base_url
        Config.LLM_FALLBACK_MODEL_NAME = self.orig_fallback_model
        Config.DEEPSEEK_THINKING_MODE = self.orig_thinking
        Config.DEEPSEEK_REASONING_EFFORT = self.orig_effort

    def test_retries_with_fallback_when_primary_fails(self):
        Config.LLM_FALLBACK_API_KEY = "fallback-key"
        Config.LLM_FALLBACK_BASE_URL = "https://api.deepseek.com"
        Config.LLM_FALLBACK_MODEL_NAME = "deepseek-v4-flash"
        _FakeOpenAI.planned = [
            {"label": "primary", "should_fail": True, "content": ""},
            {"label": "fallback", "should_fail": False, "content": "fallback ok"},
        ]

        client = llm_module.LLMClient()
        response = client.chat([{"role": "user", "content": "hello"}], temperature=0.2)

        self.assertEqual(response, "fallback ok")
        self.assertEqual(len(_FakeOpenAI.instances), 2)
        self.assertEqual(_FakeOpenAI.instances[1].api_key, "fallback-key")
        self.assertEqual(_FakeOpenAI.instances[1].base_url, "https://api.deepseek.com")
        self.assertEqual(_FakeOpenAI.instances[1].calls[0]["model"], "deepseek-v4-flash")
        self.assertNotIn("extra_body", _FakeOpenAI.instances[1].calls[0])

    def test_raises_original_error_when_fallback_also_fails(self):
        Config.LLM_FALLBACK_API_KEY = "fallback-key"
        Config.LLM_FALLBACK_BASE_URL = "https://api.deepseek.com"
        Config.LLM_FALLBACK_MODEL_NAME = "deepseek-v4-flash"
        _FakeOpenAI.planned = [
            {"label": "primary", "should_fail": True, "content": ""},
            {"label": "fallback", "should_fail": True, "content": ""},
        ]

        client = llm_module.LLMClient()

        with self.assertRaisesRegex(RuntimeError, "primary quota exceeded"):
            client.chat([{"role": "user", "content": "hello"}], temperature=0.2)


if __name__ == "__main__":
    unittest.main()
