import json
import re
from logging import getLogger

import openai

logger = getLogger(__name__)

def openai_json_fixer(jsonstr, model):
    system = """
You are a helpful assistant who is extremely skilled at identifying 
and repairing problems with JSON-formatting.
Eliminate any plain text that appears outside of the JSON object.
Respond only with well-formatted JSON.
Do not include any markup notation.
Do not include any text that is not part of the repaired JSON object.
Do not explain your decisions. 
Do not return anything except the repaired JSON object.

  """
    user = f"""
Please correct this JSON:
{jsonstr}
  """

    args = {
        "response_format": {"type": "json_object"},
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "top_p": 1,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.5,
        "stream": True,
    }
    if model.find("-1106") == -1:
        del args["response_format"]

    response = openai.chat.completions.create(**args)
    return response


def llm_json_fix(jsonstr):
    all_text = ""
    for itm in openai_json_fixer(jsonstr, "gpt-4"):
        for choice in itm.choices:
            delta = choice.delta
            content = delta.content
            if content is not None:
                all_text += content
                # print(content, end="",flush=True)
    # print("")
    return all_text


def clean_json(obj):
    if isinstance(obj, dict):
        obj = {key.strip(): clean_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        obj = [clean_json(element) for element in obj]
    elif isinstance(obj, str):
        obj = obj.strip()
    return obj


def fix_json(json_text):
    try:
        d = json.loads(json_text)
        return d
    except Exception as e:
        logger.debug(f"Error: {e}")
        need_to_fix = True
    if json_text.find("```") > -1:
        json_text = re.sub("^[^`]*```json([^`]+)```.*", r"\g<1>", json_text, flags=re.DOTALL)

    json_text = json_text.replace("json```", "")
    json_text = json_text.replace("```json", "")
    json_text = json_text.replace("```", "")
    json_text = re.sub(r"\<\/?co\:\>?", "", json_text)

    if json_text.strip()[-1] == ":":
        json_text += '""}'
        if json_text[0] == "[":
            json_text += "]"
    json_data = None
    max_error = len(json_text)
    json_text = json_text.strip()
    if json_text.find("{{") > -1:
        json_text = json_text.replace("{{", "{").replace("}}", "}")
    kill_switch = 0
    while True and kill_switch < max_error:
        kill_switch += 1
        try:
            result = json.loads(json_text)  # try to parse...
            break  # parsing worked -> exit loop
        except Exception as e:
            unexp = None
            unexp = re.findall(r"Unterminated string starting at.*\(char (\d+)\)", str(e))
            if unexp is not None and len(unexp) > 0:
                unexp = int(unexp[0])
                if json_text[unexp] == '"':
                    continue
                else:
                    json_text = json_text.replace("'", '"')
                    continue
            unexp = re.findall(r"Expecting property name enclosed.*\(char (\d+)\)", str(e))
            if unexp is not None and len(unexp) > 0:
                unexp = int(unexp[0])
                if json_text[unexp] == "'":
                    unexp += 1
                    prefx = json_text[0:unexp][0:-1]
                else:
                    prefx = json_text[0:unexp]
                sufx = json_text[unexp:]
                sparts = sufx.split(":")
                if len(sparts) > 1:
                    if sparts[0][-1] != '"':
                        if sparts[0][-1] == "'":
                            sparts[0] = sparts[0][0:-1]
                        sparts[0] = f'{sparts[0]}"'
                        sufx = ":".join(sparts)
                json_text = f'{prefx}"{sufx}'
                continue
            unexp = re.findall(r"Invalid control character.*\(char (\d+)\)", str(e))
            if unexp is not None and len(unexp) > 0:
                unexp = int(unexp[0])
                if json_text[unexp:][0] == "\n":
                    unexp -= 2
                    if json_text[unexp:][0] == "'":
                        json_text = json_text[0:unexp] + '"' + json_text[unexp + 1 :]
                    continue
            unexp = re.findall(r"Expecting value.*\(char (\d+)\)", str(e))
            if unexp is not None and len(unexp) > 0:
                unexp = int(unexp[0])
                if json_text[unexp] == "'":
                    json_text = json_text[0:unexp] + '"' + json_text[unexp + 1 :]
                continue
            unexp = re.findall(r"Extra data.*\(char (\d+)\)", str(e))
            if unexp is not None and len(unexp) > 0:
                unexp = int(unexp[0])
                if json_text[unexp:][0] == ",":
                    json_text = f"[{json_text}]"
                continue
            unexp = re.findall(r".*\':\' delimiter.*\(char (\d+)\)", str(e))
            if unexp is not None and len(unexp) > 0:
                unexp = int(unexp[0]) - 2
                prefx = json_text[0:unexp]
                sufx = json_text[unexp:]
                json_text = f'{prefx}"{sufx}'
                continue
    try:
        json_data = clean_json(json.loads(json_text))
    except Exception as e:
        raise Exception(f"{e}")
    return json_data
