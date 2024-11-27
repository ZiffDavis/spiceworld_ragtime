import json
from logging import getLogger

import openai
import requests

from utils.json_repair import fix_json

logger = getLogger(__name__)

class LLMInvoker:
    def __init__(self, llm="openai", json_output=False):
        self.json_output = json_output
        self.default_llm = llm
        self.all_text = ""
        self.last_response = ""

    def json(self):
        json_value = None
        try:
            json_value = json.loads(self.all_text)
        except Exception as e:
            logger.warning(f"failed to decode LLM response {e}")
            logger.info(f"LLM response: {self.all_text}")
            json_value = fix_json(self.all_text)
        return json_value

    def call_llm(self, prompt, model=None, stream=True):
        self.all_text = ""
        if self.default_llm == "openai":
            return self.ask_openai(prompt, model, stream)
        elif self.default_llm == "ollama":
            return self.ask_ollama(prompt)

    def pick_model(self, model):
        if self.default_llm == "openai":
            return "gpt-4o"
        elif self.default_llm == "ollama":
            return "llama3"

    def ask_llm(self, prompt, model=None, stream=True):
        model = self.pick_model(model)

        for itm in self.call_llm(prompt, model=model, stream=stream):
            if self.default_llm == "openai":
                for choice in itm.choices:
                    delta = choice.delta
                    content = delta.content
                    if content is not None:
                        self.all_text += content
                        yield content
            elif self.default_llm == "ollama":
                yield itm

    def ask_ollama(self, prompt):
        full_text = ""
        all_text = ""
        for response in requests.post(
            "http://localhost:11434/api/chat",
            stream=True,
            data=json.dumps({"model": "llama3", "messages": [{"role": "user", "content": prompt}]}),
        ):
            txt = response.decode().strip()
            all_text += txt
            try:
                data = json.loads(all_text)
                txt = data["message"]["content"]
                yield txt
                full_text += txt
                all_text = ""
            except Exception:
                # print(e)
                continue
        return full_text

    def ask_openai(self, prompt, model="gpt-4o", stream=True):
        args = {
            "response_format": {"type": "json_object"},
            "model": model,
            "messages": prompt,
            "temperature": 0.3,
            "top_p": 1,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.5,
            "stream": stream,
        }
        if not self.json_output or (model.find("-1106") == -1 and model.find("gpt-4o") == -1):
            del args["response_format"]

        response = openai.chat.completions.create(**args)
        return response
