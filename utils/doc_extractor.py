import csv
import json
import os
import re
import sys
import zipfile
from difflib import SequenceMatcher
from itertools import pairwise

# from google_helper import GoogleHelper
import pdfplumber
from bs4 import BeautifulSoup
from striprtf.striprtf import rtf_to_text
from unidecode import unidecode

from utils.doc_extractor_docx import DocExtractorDOCX
from utils.json_repair import fix_json
from utils.llm_invoker import LLMInvoker

csv.field_size_limit(sys.maxsize)


class DocExtractor:
    def __init__(self, bucket=None, brand=None):
        self.bucket = bucket
        self.brand = brand
        self.WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        self.PARA = self.WORD_NAMESPACE + "p"
        self.TEXT = self.WORD_NAMESPACE + "t"
        self.TAB = self.WORD_NAMESPACE + "tab"
        self.BR = self.WORD_NAMESPACE + "br"
        self.CR = self.WORD_NAMESPACE + "cr"
        self.LINK = self.WORD_NAMESPACE + "hyperlink"
        self.IMG_NAMESPACE = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
        self.IMG = self.IMG_NAMESPACE + "cNvPr"
        # gcs_key = os.environ["GCS_KEY"]
        # gcs_secret = os.environ["GCS_SECRET"]
        gcreds = os.environ["GSUITE_CREDS"]
        # self.google_helper = GoogleHelper(gcreds, gcs_key, gcs_secret, self.bucket, self.brand)
        # self.de_smusher = HECDeSmusher()
        self.ext_to_mime = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc": "application/msword",
            "pdf": "application/pdf",
            "txt": "text/plain",
            "rtf": "application/rtf",
            "html": "text/html",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }

    def parse_mime(self, mimetype):
        mime_to_ext = {ext_to_mime[x]: x for x in ex_to_mime}
        if mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return "docx"
        elif mimetype == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            return "pptx"
        elif mimetype == "application/msword":
            return "doc"
        elif mimetype == "application/pdf":
            return "pdf"
        elif mimetype == "text/plain":
            return "txt"
        elif mimetype == "text/rtf" or mimetype == "application/rtf":
            return "rtf"
        elif mimetype == "text/html":
            return "html"

    def extract_text(self, file_obj, mimetype=None, ext=None, doc_id=None):
        if mimetype != None and ext == None:
            ext = self.parse_mime(mimetype)
        elif ext != None and mimetype == None:
            mimetype = self.ext_to_mime[ext]
        resume_data = None
        if ext == "pdf" or ext == None:
            try:
                resume_data = self.text_from_pdf_obj(file_obj)
                ext = "pdf"
            except Exception as e:
                print(e)
        if ext == "pptx" or ext == None:
            try:
                resume_data = self.text_from_pptx_obj(file_obj)
                ext = "pdf"
            except Exception as e:
                print(e)
        if ext == "docx" or ext == None:
            try:
                resume_data = self.text_from_docx_obj(file_obj)
                ext = "docx"
            except Exception as e:
                print(e)
        if ext == "rtf" or ext == None:
            try:
                resume_data = self.text_from_rtf_obj(file_obj)
                ext = "rtf"
            except Exception as e:
                print(e)
        if ext == "html" or ext == None:
            try:
                resume_data = self.text_from_html_obj(file_obj)
                ext = "html"
            except Exception as e:
                print(e)
        if ext == "txt" or ext == None:
            try:
                resume_data = self.text_from_txt_obj(file_obj)
                ext = "txt"
                if resume_data.find("function()") > -1 and resume_data.find("{") > -1:
                    resume_data = None
            except Exception as e:
                print(e)
        if ext == "doc" or ext == None:
            try:
                resume_data = self.text_from_doc_obj(file_obj)
                ext = "doc"
            except Exception as e:
                print(e)
        # if resume_data!=None:
        #   resume_data = self.cleanse_text(resume_data)
        return resume_data

    def text_from_pptx_file(self, path):
        pptxFileObj = open(path, "rb")
        return self.text_from_pptx_obj(pptxFileObj)

    def text_from_pdf_file(self, path):
        pdfFileObj = open(path, "rb")
        return self.text_from_pdf_obj(pdfFileObj)

    def text_from_pdf_obj(self, pdfFileObj):
        content = []
        pdf = pdfplumber.open(pdfFileObj)
        for page in pdf.pages:
            text = unidecode(page.extract_text(), errors="replace", replace_str=" ")
            content += text.split("  ")
        return content

    def text_from_docx_file(self, path, include_images=False):
        docObj = open(path, "rb")
        return self.text_from_docx_obj(docObj, include_images)

    def text_from_pptx_obj(sefl, docObj):
        slide_text = {}
        toc = {}
        with zipfile.ZipFile(docObj) as docx:
            filelist = docx.namelist()
            filelist = [f for f in filelist if re.match(r".*slides/slide[0-9]+.xml", f)]
            for fname in filelist[1:]:
                is_toc = False
                if re.match(r".*slides/slide[0-9]+.xml", fname):
                    slide_name = fname.split("/")[-1]
                    lines = []
                    txt = docx.read(fname)
                    soup = BeautifulSoup(txt, features="xml")
                    lists = soup.find_all("a:p")
                    for l in lists:
                        txt = l.get_text(separator=" ")
                        txt = unidecode(txt, errors="replace", replace_str=" ")
                        txt = txt.strip()
                        no_punc = re.sub(r"[^A-Za-z ]", " ", txt).lower()

                        if len(toc) == 0 and (
                            txt.lower().find("table of contents") > -1 or txt.lower().find("agenda") > -1
                        ):
                            is_toc = True
                            slide_name = "Table of Contents"
                        elif len(toc) > 0 and no_punc in toc:
                            slide_name = txt
                        elif len(txt) > 1 and re.match(r".*[a-z]+", txt):
                            lines.append(txt)
                    if len(lines) > 0:
                        slide_text[slide_name] = lines
                        if is_toc:
                            toc = {re.sub(r"[^A-Za-z ]", " ", x).lower(): 1 for x in lines}
        return slide_text

    def text_from_docx_obj(self, docObj, include_images):
        de_docx = DocExtractorDOCX()
        content_json = de_docx.process_file_obj(docObj, include_images)
        return content_json

    def text_from_doc_file(self, path):
        docObj = open(path, "rb")
        return self.text_from_doc_obj(docObj)

    def text_from_doc_obj(self, docObj):
        content = docObj.read()
        isdoc = False
        try:
            content = content.decode("utf-8")
        except:
            isdoc = True
        text = []
        if not isdoc and content.find("\\rtf1") > -1:
            text = rtf_to_text(content)
            resume_data = text.split("\n")
            return resume_data
        else:
            file = self.hecgoogle.save_as_google_doc(docObj)
            content = self.hecgoogle.get_document_text(file["id"])
            resume_data = content.split("\n")
            return resume_data

    def text_from_txt_file(self, path):
        txtObj = open(path, "rb")
        return self.text_from_txt_obj(txtObj)

    def text_from_txt_obj(self, txtObj):
        txt = txtObj.read()
        txt = txt.decode()
        return txt.split("\n")

    def text_from_html_file(self, path):
        htmlObj = open(path, "r")
        return self.text_from_html_obj(htmlObj)

    def text_from_html_obj(self, htmlObj):
        html = str(htmlObj.read())
        soup = BeautifulSoup(html, features="html.parser")
        for data in soup(
            [
                "nav",
                "figcaption",
                "footer",
                "aside",
                "head",
                "svg",
                "path",
                "circle",
                "link",
                "form",
                "style",
                "img",
                "style",
                "script",
            ]
        ):
            data.decompose()
        resume_text = soup.get_text(separator=" ").splitlines()
        return resume_text

    def text_from_rtf_file(self, path):
        docObj = open(path, "rb")
        return self.text_from_doc_obj(docObj)

    def text_from_rtf_obj(self, docObj):
        content = docObj.read()
        content = content.decode("utf-8")
        text = rtf_to_text(content)
        resume_data = text.split("\n")
        return resume_data

    def close_gaps(self, line):
        old_line = line
        # line = self.de_smusher.dedupe_line(line)
        line = self.de_smusher.edit_spaces_in_line(line)
        # line = self.de_smusher.de_smush_line(line)
        line = line.replace("\0", "")
        line = line.replace(" x ra y", " x-ray ")
        line = line.replace(" x ra ", " x-ray ")
        line = line.replace(" roux en y ", " roux-en-y ")
        line = re.sub("([a-z])([A-Z][a-z])", r"\g<1> \g<2>", line)
        return line

    def cleanse_text(self, resume_data):
        itm_lines = []
        for text in resume_data:
            text = text.replace("\t\r", " ")
            text = text.replace("•", "\n• ")
            text = re.sub("( o )+", r" \* ", text)
            text = text.replace(" * ", "\n")
            lines = text.split("\n")
            for line in lines:
                line = unidecode(line, errors="replace", replace_str=" ")
                line = re.sub(r"https?\:[-a-zA-Z0-9@:%._\/\+~#=]+", "", line)
                # line = self.close_gaps(line)
                if len(line) == 0:
                    continue
                if line.strip() == "•":
                    continue
                line = re.sub(r"^\* ", " ", line)
                if line != "*":
                    line = f"{line}"
                    line = line.replace("", "\n")
                    line = line.replace("­", "")
                    line = line.replace(" ", " ")
                    line = line.replace("-‐", "-")
                    line = re.sub("[ ]+", " ", line)
                    line = re.sub("[\t]+", " ", line).strip()
                    line = re.sub("[ ]+", " ", line)
                    pattern = r"\b([A-Z]+[\s_]){1:}\b"
                    line = re.sub(pattern, r"\n\g<1>\n", line)
                    if line.isupper():
                        line = f"\n{line}\n"
                    elif len(line) > 0 and len(line.split(" ")) < 3 and line[-1] == ":":
                        line = f"\n{line}\n"
                    itm_lines.append({"text": line})
        text_content = "\n".join([x["text"] for x in itm_lines])
        text_content = re.sub("\n\n[\n+]", "\n\n", text_content).strip()
        if len(text_content) == 0:
            text_content = None
        return text_content

    def json_from_list(self, content):
        if isinstance(content, list):
            subsequences = []
            for x, y in pairwise(content):
                s = SequenceMatcher(None, x, y)
                s = s.get_matching_blocks()[0]
                if s.a == s.b:
                    subsequences.append([s.a, s.size])
            new_content = {}
            for i in range(0, len(content)):
                if i < len(subsequences):
                    sub = subsequences[i]
                    content[i] = content[i][0 : sub[0]] + content[i][sub[0] + sub[1] :]
                    new_content[f"part_{i}"] = content[i]
                else:
                    new_content[f"part_{i}"] = content[i]
            msg = f"""You're a helpful assistant who can organize and format 
  JSON so that it makes more sense and is more intuitive.
  Given the following JSON object, please reply with new JSON that is
   more contextually relevant. Please respond with JSON where the old key is a key in the JSON and your proposed new key as its value:
  Also clean up any repeating characters, like long trails of periods.
  
  EXAMPLE:
  INPUT JSON: {{"part_11":["apples","oranges","bananas"],"part_2":["cats","dogs"]}}
  RECOMMENDED KEYS: {{"part_11":"fruits", "part_2":"pets"}}

  DO NOT RECREATE THE ENTIRE JSON, JUST PROVIDE YOUR RECOMMENDATIONS FOR NEW KEYS AS DEMONSTRATED IN THE EXAMPLE.
  PLEASE MAKE SURE THE ORIGINAL KEYS ARE UNCHANGED. DO NOT ADD SPACES OR UNDERSCORES.
  DO NOT INCLUDE ANY ADDITIONAL COMMENTS OR DESCRIPTIONS OF YOUR REASONING.
  ONLY RESPOND WITH YOUR RECOMMENDATIONS IN JSON FORM.
  
  INPUT JSON: {json.dumps({x:new_content[x][0:100] for x in new_content})}.
  RECOMMENDED KEYS:
  """
            llm_invoker = LLMInvoker("ollama")
            all_txt = ""
            for txt in llm_invoker.ask_llm(msg):
                all_txt += txt
                # print(txt,end="",flush=True)
            data = fix_json(all_txt)
            final_content = {}
            for x in data:
                y = data[x]
                final_content[y] = new_content[x]

            return final_content
        elif isinstance(content, dict):
            return content
        else:
            return content

    def process_object(self, filename=None, fileobj=None, ext=None, include_images=False):
        if ext == None and filename != None and filename.find(".") > -1:
            ext = os.path.splitext(filename)[1].replace(".", "")
            print(ext)
        text_content = None
        if ext == "pdf":
            text_content = self.text_from_pdf_obj(fileobj)
        elif ext == "rtf":
            text_content = self.text_from_rtf_obj(fileobj)
        elif ext == "doc":
            text_content = self.text_from_doc_obj(fileobj)
        elif ext == "pptx":
            text_content = self.text_from_pptx_obj(fileobj)
        elif ext == "docx":
            text_content = self.text_from_docx_obj(fileobj, include_images=include_images)
        elif ext == "html":
            text_content = self.text_from_html_obj(fileobj)
        elif ext == "txt":
            text_content = self.text_from_txt_obj(fileobj)
        return text_content

    def process_file(self, filename=None, ext=None, include_images=False):
        if ext == None and filename != None and filename.find(".") > -1:
            ext = os.path.splitext(filename)[1].replace(".", "")
            print(ext)
        text_content = None
        if ext == "pdf":
            text_content = self.text_from_pdf_file(filename)
        elif ext == "rtf":
            text_content = self.text_from_rtf_file(filename)
        elif ext == "doc":
            text_content = self.text_from_doc_file(filename)
        elif ext == "pptx":
            text_content = self.text_from_pptx_file(filename)
        elif ext == "docx":
            text_content = self.text_from_docx_file(filename, include_images=include_images)
        elif ext == "html":
            text_content = self.text_from_html_file(filename)
        elif ext == "txt":
            text_content = self.text_from_txt_file(filename)
            text_content = [x for x in text_content if len(x.strip()) > 0]
        return self.json_from_list(text_content)


if __name__ == "__main__":
    de = DocExtractor()
    text_content = de.process_file("KFC_W4 Partnership Brief - Final 5.9.24.pdf")
    with open("doc_text.json", "w") as fout:
        fout.write(json.dumps(text_content, indent=4))
    # for l in text_content:
    #   print(l)
    # print(text_content)
