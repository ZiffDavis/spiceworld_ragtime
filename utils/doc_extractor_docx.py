import math
import os
import re
import zipfile
from collections import Counter

from bs4 import BeautifulSoup
from PIL import Image
from unidecode import unidecode


class DocExtractorDOCX:
    def __init__(self):
        self.links = {}
        self.images = {}

    def is_heading(self, para):
        txt = para.get_text().strip()
        txt = re.sub(r"[^A-Za-z ]", "", txt)
        txt = txt.strip()
        if len(txt) == 0:
            return False
        style_name = self.get_style(para)
        if style_name is not None:
            if "Heading" in style_name:
                return True
        para_prop = para.find("pPr")
        if para_prop is not None:
            justify = para_prop.find("jc")
            if justify is not None:
                if justify["w:val"] == "center":
                    if len(txt.split(" ")) < 10:
                        return True
        k = len(re.findall(r"[a-z]", txt))
        if k == 0 and len(txt.split(" ")) > 0:
            return True
        return False

    def is_toc(self, para):
        style_name = self.get_style(para)
        if style_name is not None:
            return False
        if "TOC" in style_name:
            return True

    def get_style(self, para):
        props = para.find_all("pPr")
        for prop in props:
            style = prop.find("pStyle")
            if style is not None:
                style_name = style["w:val"]
                return style_name

    def has_toc(self, paras):
        for para in paras:
            style_name = self.get_style(para)
            if style_name is None:
                continue
            if "TOC" in style_name:
                return True

    def max_toc_level(self, paras):
        levels = []
        for para in paras:
            style_name = self.get_style(para)
            if style_name is None:
                continue
            if "TOC" in style_name and "Heading" not in style_name:
                level = int(style_name.replace("TOC", ""))
                levels.append(level)
        return min(levels)

    def flatten_json(self, nested_json, prefix="", output_dict=None):
        """Flattens a nested JSON structure into a single-level dictionary with keys reflecting the path.

        Args:
                nested_json (dict): The nested JSON structure to flatten.
                prefix (str): The current key prefix to use for flattened keys.
                output_dict (dict): The dictionary to accumulate flattened results.

        Returns:
                dict: The flattened JSON dictionary.
        """
        if output_dict is None:
            output_dict = {}
        if not isinstance(nested_json, dict):
            output_dict[prefix.replace(" - text", "")] = nested_json
            return output_dict

        for key, value in nested_json.items():
            new_prefix = prefix + " - " + key if prefix else key
            self.flatten_json(value, new_prefix, output_dict)
        return output_dict

    def populate_structured_json(self, paras, json_doc, max_toc, links):
        """Converts XML structure with Header elements into nested JSON."""
        tmp_doc = json_doc

        def process_element(paras, tmp_doc, level, links):
            result = tmp_doc
            index = 0
            header_title = None
            header_level = level
            for child in paras:
                index += 1
                style_name = self.get_style(child)
                if style_name is not None and "TOC" not in style_name and "Heading" in style_name:
                    header_level = int(style_name.replace("Heading", ""))
                    header_title = child.get_text()
                    if header_level == level:
                        result[header_title] = process_element(paras[index:], result[header_title], level + 1, links)
                elif header_level < level:
                    return result
                else:  # Non-header elements (assumed to be text content)
                    if level != header_level:
                        continue
                    txt = []
                    for tag in child.find_all():
                        if tag is not None and "text" in result and header_title is None:
                            if tag.name == "t":
                                tagtxt = tag.get_text().strip()
                                txt.append(unidecode(tagtxt, errors="replace", replace_str=" "))
                            elif tag.name == "hyperlink":
                                link_id = tag.get("r:id", None)
                                if link_id is not None:
                                    txt.append(f" ({links[tag['r:id']]}) ")
                            elif tag.name == "blip":
                                img_id = tag["r:embed"]
                                if img_id in self.image_ref:
                                    txt.append(f" [INSERT_IMAGE: {image_ref[img_id]}] ")
                            elif tag.name == "cNvPr":
                                txt += f" [INSERT_IMAGE: {tag['name']}] "
                    if len(txt) > 0:
                        result["text"] = txt
            return result

        return process_element(paras, tmp_doc, max_toc, links)

    def toc_list_to_json(self, toc_list, max_toc):
        def process_item(items, level=max_toc):
            result = {}
            current_section = None
            for item in items:
                style_name = self.get_style(item)
                if style_name is None:
                    continue
                if "TOC" in style_name and "Heading" not in style_name:
                    item_level = int(style_name.replace("TOC", ""))
                    item_title = item.find("t").get_text()  # Extract the title
                    if item_level == level:  # New section at the current level
                        current_section = {"text": []}
                        result[item_title] = current_section
                    elif item_level > level and current_section:  # Sub-section
                        current_section.update(process_item([item], level + 1))
            return result

        return process_item(toc_list)

    def process_structured_doc(self, paras, links):
        max_toc = self.max_toc_level(paras)
        json_doc = self.toc_list_to_json(paras, max_toc)
        json_doc = self.populate_structured_json(paras, json_doc, max_toc, links)
        json_doc = self.flatten_json(json_doc)
        # print(json.dumps(json_doc,indent=4))
        return json_doc

    def get_common_sizes(self, paras):
        sizes = []
        for para in paras:
            sect = para.find("sectPr")
            if sect is not None:
                continue
            runs = para.find_all("r")
            for run in runs:
                props = run.find_all("rPr")
                for prop in props:
                    px = prop.prefix
                    sz = prop.find("sz")
                    if sz is None:
                        continue
                    sz = int(math.floor(float(sz[f"{px}:val"])))
                    sizes.append(sz)
        sizes = Counter(sizes).most_common()
        return sizes

    def save_images(self, docx, include_images):
        # print(include_images)
        images = {}
        filelist = docx.namelist()
        for fname in filelist:
            _, extension = os.path.splitext(fname)
            if extension in [".jpg", ".jpeg", ".png", ".bmp"] and include_images:
                dst_fname = os.path.join("doc_images", os.path.basename(fname))
                if not os.path.exists("doc_images"):
                    os.mkdir("doc_images")
                with open(dst_fname, "wb") as dst_f:
                    dst_f.write(docx.read(fname))
                    try:
                        # Opent the image to ensure it's valid
                        Image.open(dst_fname)
                        img_name = fname.split("/")[-1]
                        images[img_name] = 1
                    except Exception:
                        os.unlink(dst_fname)
                        continue
        return images

    def extract_links(self, docx):
        links = {}
        filelist = docx.namelist()
        for fname in filelist:
            if fname.find("xml.rels") > -1 or fname.find("xml._rels") > -1:
                txt = docx.read(fname)
                soup = BeautifulSoup(txt, features="xml")
                rels = soup.find_all("Relationship")
                for r in rels:
                    if r.get("TargetMode", None) is not None:
                        if r.get("Id", None) is not None:
                            links[r.get("Id")] = r.get("Target")
        return links

    def guess_current_section(self, para, default_size):
        runs = para.find_all("w:r")
        if self.is_heading(para):
            txt = para.get_text().strip()
            return txt
        for run in runs:
            props = run.find_all("w:rPr")
            for prop in props:
                px = prop.prefix
                sz = prop.find(f"{px}:sz")
                if sz is None:
                    continue
                sz = int(math.floor(float(sz[f"{px}:val"])))
                b = prop.find("b")
                if b is not None:
                    b = int(b.get(f"{px}:val", 0))
                else:
                    b = 0
                if len(runs) == 1 and (int(sz) > default_size or b == 1):
                    txt = run.get_text().strip()
                    txt = unidecode(txt, errors="replace", replace_str=" ")
                    if len(txt.split(" ")) > 10:
                        continue
                    if len(txt) > 1:
                        if para.parent.name == "body":
                            return txt

    def process_folder(self, include_images=True):
        dirlist = os.listdir("documents")
        for f in dirlist:
            if f.find(".docx") == -1 or f.find("~") > -1:
                continue
            self.process_file(f, include_images)

    def process_file(self, f, include_images=True):
        json_doc = {}
        with open(f"documents/{f}", "rb") as fin:
            json_doc = self.process_file_obj(fin, include_images)
            json_doc["FILENAME"] = f
        return json_doc

    def process_file_obj(self, fin, include_images=True):
        json_doc = {}
        with zipfile.ZipFile(fin) as docx:
            self.image_ref = {}
            images = self.save_images(docx, include_images)
            links = self.extract_links(docx)

            txt = docx.read("word/_rels/document.xml.rels")
            soup = BeautifulSoup(txt, features="xml")
            for tag in soup.find_all("Relationship"):
                type = tag["Type"]
                if type.find("image") > -1:
                    image_id = tag["Id"]
                    image_target = tag["Target"].split("/")[-1]
                    if image_target in images:
                        self.image_ref[image_id] = image_target

            txt = docx.read("word/document.xml")
            soup = BeautifulSoup(txt, features="xml")
            paras = soup.find_all("p")
            toc_exists = self.has_toc(paras)
            if toc_exists:
                json_doc = self.process_structured_doc(paras, links)
                return json_doc
            common_sizes = self.get_common_sizes(paras)
            if len(common_sizes) > 0:
                default_size = common_sizes[0][0]
            else:
                default_size = 0

            current_section = "UNCATEGORIZED"
            json_doc["UNCATEGORIZED"] = []
            for para in paras:
                sect = para.find("sectPr")
                if sect is not None:
                    continue
                txt = self.guess_current_section(para, default_size)
                if txt not in json_doc and txt is not None:
                    json_doc[txt] = []
                    current_section = txt
                    continue
                run_tags = para.find_all()
                txt = []
                for tag in run_tags:
                    if tag.name == "t":
                        txt.append(tag.get_text(separator=" ").strip())
                    elif tag.name == "blip":
                        img_id = tag["r:embed"]
                        if img_id in self.image_ref:
                            txt.append(f" [INSERT_IMAGE: {self.image_ref[img_id]}] ")
                    elif tag.name == "hyperlink":
                        link_id = tag.get("r:id", None)
                        if link_id is not None:
                            txt.append(f" ({links[tag['r:id']]}) ")
                txt = " ".join(txt)
                if txt == current_section or len(txt.strip()) == 0:
                    continue
                txt = unidecode(txt, errors="replace", replace_str=" ")
                if len(txt) > 0:
                    json_doc[current_section].append(txt)
            return json_doc


if __name__ == "__main__":
    de = DocExtractorDOCX()
    de.process_folder()
