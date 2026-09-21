import os
import platform


if platform.system().lower() in {"windows", "darwin"}:
    _DEFAULT_MODEL_URL = "http://llm.demo.haizhi.com/v1/chat/completions"
    _DEFAULT_MODEL_NAME = "deepseek-v4-flash"
else:
    _DEFAULT_MODEL_URL = "http://10.104.129.83:8088/v1/chat/completions"
    _DEFAULT_MODEL_NAME = "deepseek-ai/DeepSeek-V3.2"

MODEL_URL = os.environ.get("MODEL_URL", _DEFAULT_MODEL_URL)
MODEL_KEY = os.environ.get(
    "MODEL_KEY",
    "sk-mvhqklhflbmcvfzjvqictcvulekolaltxyevzaxhektndhau",
)
DOCUMENT_MODEL_NAME = os.environ.get("DOCUMENT_MODEL_NAME", _DEFAULT_MODEL_NAME)
