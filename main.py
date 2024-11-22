from datetime import datetime
import os
import json
import click
from unidecode import unidecode
import psycopg2
import warnings
from pydantic import BaseModel
from utils.llm_invoker import LLMInvoker
import sys

def get_db():
	db = psycopg2.connect(
		password=os.environ["DATABASE_PASS"],
		user=os.environ["DATABASE_USER"], 
		database=os.environ["DATABASE_DATABASE"], 
		host=os.environ["DATABASE_HOST"],
		connect_timeout=3)
	db.autocommit = True
	return db

@click.group()
def group():
    pass

def split_text(text, max_length=255):
  chunks = []
  current_chunk = ""
  for word in text.split():
    if len(current_chunk) + len(word) + 1 <= max_length:
      current_chunk += word + " "
    else:
      chunks.append(current_chunk.rstrip())
      current_chunk = word + " "
  if current_chunk:
    chunks.append(current_chunk.rstrip())
  return chunks


@click.command()
@click.option('--include_images','-i', default=False, is_flag = True)
@click.option('--force_overwrite','-f', default=False,is_flag = True)
@click.option("--config", default="None", prompt = "Config file name")
@click.option("--file", default="None", prompt = "Doc name (source of documents if it exists)")
@click.option("--folder", default="None", prompt = "Document directory name")
def build_docs(**kwargs):
	config = None
	for k in kwargs:
		if kwargs[k]=="None":
			kwargs[k] = None
	include_images = kwargs["include_images"]
	config_file = kwargs["config"]
	file = kwargs["file"]
	folder = kwargs["folder"]
	force_overwrite = kwargs["force_overwrite"]
	if not config_file and not file and not folder:
		click.echo("You must supply a config file and a doc source file or folder.")
		return
	elif config_file and not (file or folder):
		click.echo("You must supply a config file and a doc source file or folder.")
		return
	elif file and folder:
		click.echo(f"Move {file} into {folder} and just provide the folder option.")
		return
	elif config_file:
		if config_file.find(".json")==-1:
			click.echo(f"Config files must be in JSON format.")
			return
		try:
			with open(config_file,"r") as fin:
				config = json.load(fin)
		except Exception as e:
			click.echo(f"Problem opening config file: {e}")
			return
		if "content_settings" not in config:
			click.echo(f"No \"content_settings\" key found in config file.")
			return
		if "document_file" not in config["content_settings"]:
			click.echo(f"No \"document_file\" key found in config file.")
			return

		click.echo("Loading doc extractor...")
		from utils.doc_extractor import DocExtractor
		from utils.llm_invoker import LLMInvoker
		de = DocExtractor()
		doc_file = config["content_settings"]["document_file"]
		doc_json = {}
		if file:
			click.echo(f"Parsing \"{file}\" to \"{doc_file}\"...")
			doc_json = de.process_file(file, include_images=include_images)
		elif folder:
			click.echo(f"Parsing files in \"{folder}\" to \"{doc_file}\"...")
			dirlist = os.listdir("documents")
			for f in dirlist:
				print(f)
				if f.find("~")==-1:
					fname = f"{folder}/{f}"
					content = de.process_file(fname, include_images=True)
					if content == None:
						continue
					for k in content:
						newk = k
						counter = 1
						if k=="UNCATEGORIZED":
							continue
						while newk in doc_json:
							counter+=1
							newk = f"{k}_{counter}"
						if len(content[k]) > 0:
							doc_json[newk] = content[k]
		uuid=1
		doc_data = {}
		for key in doc_json:
			if isinstance(doc_json[key],list):
				doc_json[key] = "\n".join(doc_json[key])
			if key.lower().find("table of contents")>-1:
				continue
			pretty_key = key.replace("_"," ").title()
			if (len(doc_json[key].strip())==0):
				continue
			doctext = doc_json[key]
			if len(doctext)<=255:
				content = f"Section: {pretty_key}\nContent: {doc_json[key]}"
				content = unidecode(content, errors='replace', replace_str=u' ')
				doc_data[f"uuid_{uuid}"] = content
				uuid+=1
			else:
				text_array = split_text(doctext)
				for t in text_array:
					content = f"Section: {pretty_key}\nContent: {t}"
					content = unidecode(content, errors='replace', replace_str=u' ')
					doc_data[f"uuid_{uuid}"] = content
					uuid+=1


		with open(doc_file,"w") as fout:
			fout.write(json.dumps(doc_data,indent=4))
			



@click.command()
@click.option("--config", default="None", prompt = "Config file name")
def index_docs(**kwargs):
	config = None
	docs = None
	for k in kwargs:
		if kwargs[k]=="None":
			kwargs[k] = None
	config_file = kwargs["config"]
	if not config_file:
		click.echo("Please specify a config file name.")
		return
	try:
		with open(config_file,"r") as fin:
			config = json.load(fin)
	except Exception as e:
		click.echo(f"Error loading config file: {e}")
		return

	if "content_settings" not in config:
		click.echo(f"No \"content_settings\" key found in config file.")
		return
	if "document_file" not in config["content_settings"]:
		click.echo(f"No \"document_file\" key found in \"content_settings.")
		return
	doc_file = config["content_settings"]["document_file"]
	if "vector_store_location" not in config:
		click.echo("No \"vector_store_location\" key in config (value must be either \"database\" or \"local\"")
		return
	vector_store_location = config["vector_store_location"]

	if (vector_store_location=="local"):
		if "local_settings" not in config:
			click.echo("No \"local_settings\" key in config.")
			return
		local_config = config["local_settings"]
		vector_store_directory = local_config["vector_store_folder"]
		index_name = local_config["index_name"]
	elif (vector_store_location=="database"):
		use_environment_variables = input("Use database environment variables (Y/N)?")
		if (use_environment_variables.lower()!="y"):
			use_environment_variables = True
		else:
			use_environment_variables = False
		if "database_settings" not in config:
			click.echo("No \"database_settings\" key in config.")
			return
		data_config = config["database_settings"]
		if "content_table_name" not in data_config:
			click.echo("No \"content_table_name\" key in config[\"database_settings\"].")
			return
		content_table = data_config["content_table_name"]
		if not use_environment_variables:
			try:
				host = data_config["database_host"]
				os.environ["DATABASE_HOST"] = host
				user = data_config["database_user"]
				os.environ["DATABASE_USER"] = host
				password = data_config["database_pass"]
				os.environ["DATABASE_PASS"] = host
				database = data_config["database_database"]
				os.environ["DATABASE_DATABASE"] = host
			except:
				click.echo("Could not find database settings in config.")
				return

	try:
		with open(doc_file,"r") as fin:
			docs = json.load(fin)
	except Exception as e:
		click.echo(f"Error loading config file: {e}")
		return

	formatted_content = []
	if "text_has_labels" in config["content_settings"] and config["content_settings"]["text_has_labels"]:
		
		if "label_order" not in config["content_settings"]:
			click.echo(f"No \"label_order\" key found in \"content_settings\".")
			return
		if "editor_fields" not in config["content_settings"]:
			click.echo(f"No \"editor_fields\" key found in \"content_settings\".")
			return
		editor_fields = config["content_settings"]["editor_fields"]

		content_fields = []
		for f in editor_fields:
			if "is_content" in editor_fields[f]:
				content_fields.append(f)
		if len(content_fields)>1:
			click.echo("Only one editor field can have the \"is_content\" flag set to \"true\".")
			return
		
		for doc_id in docs:
			content = docs[doc_id]
			formatted_content.append({"id":doc_id,"text":content})
			
	documents = []
	from llama_index.core import Document
	for doc in formatted_content:
		text = doc["text"]
		doc = Document(text = text, extra_info = {"id":doc["id"]})
		documents.append(doc)

	if vector_store_location=="database":
		from utils.pgvector_helper import PGVectorHelper
		pgindex = PGVectorHelper()
		pgindex.build_index_from_docs(documents,content_table)
	else:
		from utils.tafi_indexer import TafiIndexer
		ti = TafiIndexer(persist_dir = vector_store_directory)
		ti.index_from_docs(docs = documents,index_name = index_name)

@click.command()
@click.option("--config", default="None", prompt = "Config file name")
def query(**kwargs):
	config = None
	docs = None
	for k in kwargs:
		if kwargs[k]=="None":
			kwargs[k] = None
	config_file = kwargs["config"]
	if not config_file:
		click.echo("Please specify a config file name.")
		return
	try:
		with open(config_file,"r") as fin:
			config = json.load(fin)
	except Exception as e:
		click.echo(f"Error loading config file: {e}")
		return
	if "vector_store_location" not in config:
		click.echo("No \"vector_store_location\" key in config (value must be either \"database\" or \"local\"")
		return
	vector_store_location = config["vector_store_location"]
	if (vector_store_location=="local"):
		if "local_settings" not in config:
			click.echo("No \"local_settings\" key in config.")
			return
		local_config = config["local_settings"]
		vector_store_directory = local_config["vector_store_folder"]
		index_name = local_config["index_name"]
	elif (vector_store_location=="database"):
		use_environment_variables = input("Use database environment variables (Y/N)?")
		if (use_environment_variables.lower()!="y"):
			use_environment_variables = True
		else:
			use_environment_variables = False
		if "database_settings" not in config:
			click.echo("No \"database_settings\" key in config.")
			return
		data_config = config["database_settings"]
		if "content_table_name" not in data_config:
			click.echo("No \"content_table_name\" key in config[\"database_settings\"].")
			return
		content_table = data_config["content_table_name"]
		if not use_environment_variables:
			try:
				host = data_config["database_host"]
				os.environ["DATABASE_HOST"] = host
				user = data_config["database_user"]
				os.environ["DATABASE_USER"] = host
				password = data_config["database_pass"]
				os.environ["DATABASE_PASS"] = host
				database = data_config["database_database"]
				os.environ["DATABASE_DATABASE"] = host
			except:
				click.echo("Could not find database settings in config.")
				return

	if vector_store_location=="database":
		from utils.pgvector_helper import PGVectorHelper
		index = PGVectorHelper()
	else:
		warnings.simplefilter("ignore")
		from utils.tafi_indexer import TafiIndexer
		index = TafiIndexer(persist_dir = vector_store_directory)

	llm = LLMInvoker()
	while(True):
		q = input("] ")
		if q=="quit":
			print("\nGoodbye!\n")
			sys.exit(1)
		if vector_store_location == "database":
			warnings.simplefilter("ignore")
			response = pgindex.query_index(content_table, q)
		else:
			warnings.simplefilter("ignore")
			response = index.query(index_name = index_name, query_string = q)
		query_results = [r.text for r in response]
		system = None
		if "prompt_settings" in config:
			if "system_prompt_template" in config["prompt_settings"]:
				with open(config["prompt_settings"]["system_prompt_template"],"r") as fin:
					system = fin.read()
					system = system.format(query_results = query_results)
		else:
			system = f"""You are a helpful assistant with access to this information: 
{ptext}
When responding from user queries YOU MUST RESTRICT YOUR RESPONSE the provided information.
"""
		print("")
		user = q
		prompt = [{"role":"system","content":system},{"role":"user","content":user}]
		for text in llm.ask_llm(prompt):
			print(text, end="", flush = True)
		print("")
		print("")
group.add_command(build_docs)
group.add_command(index_docs)
group.add_command(query)

if __name__=="__main__":
	group()

		