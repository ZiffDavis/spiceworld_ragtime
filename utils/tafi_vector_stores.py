import os
from pydantic import BaseModel
import warnings
from llama_index.embeddings.langchain import LangchainEmbedding

from llama_index.core import Document
from llama_index.core import StorageContext,ServiceContext,get_response_synthesizer
from langchain_community.embeddings import HuggingFaceEmbeddings
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core import VectorStoreIndex

from llama_index.core import (
    SimpleDirectoryReader,
    load_index_from_storage
)
from llama_index.core.node_parser import JSONNodeParser
from langchain_community.vectorstores import redis
import json
import psycopg2
redis._check_redis_module_exist = lambda *args: True


class TafiVectorStore:
	index_type = None

	def __init__(self, persist_dir = None, embed_model = "sentence-transformers/all-MiniLM-L6-v2"):
		self.embed_model = embed_model
		self.persist_dir = persist_dir

	def add_to_index(self, docs = None, index = None, index_name = None, with_llm = False):
		if index==None and index_name!=None:
			index = self.load_index(index_name, with_llm)
		if index==None and index_name==None:
			raise Exception(f"{self.__class__}: Missing parameter - expected index or index_name.")
		parser = self.get_node_parser()
		new_nodes = parser.get_nodes_from_documents(docs)
		service_context = self.get_service_context(with_llm)
		index.insert_nodes(new_nodes, include_embeddings = True, show_progress = True, service_context = service_context)

	def index_from_docs(self, docs = None, index_name = None, with_llm = False):
		storage_context = StorageContext.from_defaults(
			vector_store = self.get_vector_store(index_name = index_name)
		)
		service_context = self.get_service_context(with_llm)
		index = VectorStoreIndex.from_documents(docs,
													include_embeddings=True,
													storage_context=storage_context,
													service_context=service_context,
													show_progress=True
													)
		return index

	def get_node_parser(self):
		return SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=20)

	def get_service_context(self, with_llm):
		embed_model = self.get_embed_model()
		if with_llm:
			llm = self.get_llm()
		else:
			llm = None
		node_parser = self.get_node_parser()
		service_context = ServiceContext.from_defaults(
			embed_model=embed_model,
			llm=llm,
			node_parser=node_parser
		)
		return service_context

	# THIS ADDS LLM GOVERNANCE TO SEMANTIC SEARCH.
	# FEELS LIKE OVERKILL.
	def get_llm(self):
		return VertexAI(model_name="text-bison", max_output_tokens=2048)

	def get_embed_model(self):
	   return LangchainEmbedding(HuggingFaceEmbeddings(model_name=self.embed_model))


class TafiSimpleVectorStore(TafiVectorStore):
	index_type = "file"

	def get_vector_store(self, index_name):
		pass

	def file_metadata(self, filename):
		with open(filename,"r") as fin:
			data = json.load(fin)
		#data["filename"] = filename
		return data

	def index_from_docs(self, docs = None, index_name = None, with_llm = False):
		print("INDEXING FROM DOCS")
		index = VectorStoreIndex.from_documents(documents = docs, index_id = index_name)
		return index

	def load_index(self, index_id = None, with_llm=False):
		index = None
		try:
			storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
			if index_id == None:
				index = load_index_from_storage(storage_context)
			else:
				index = load_index_from_storage(storage_context, index_id = index_id)
		except Exception as e:
			print(f"COULDN'T LOAD ({e})")
			index = None
		return index

class TafiPGVectorStore(TafiVectorStore):
	index_type = "pgvector"
	def get_vector_store(self, index_name):
		os.environ["PGVECTOR_VECTOR_SIZE"] = "384"
		vector_store = PGVectorStore.from_params(
			database=os.environ["PG_DB_DBASE"],
			host=os.environ["PG_DB_HOST"],
			password=os.environ["PG_DB_PASS"],
			port=5432,
			user=os.environ["PG_DB_USER"],
			table_name=index_name,
			embed_dim=384
		)
		logger.info("postgres vector store loaded")
		return vector_store

	def load_index(self, index_name, with_llm = True):
		return VectorStoreIndex.from_vector_store(vector_store=self.get_vector_store(index_name), service_context=self.get_service_context(with_llm))


class TafiRedisVectorStore(TafiVectorStore):
	index_type = "redis"
	def get_vector_store(self, index_name, metadata_fields):
		redis_endpoint = os.getenv("REDIS_ENDPOINT", "redis://34.70.63.211:6379")
		logger.info(f"Using redis endpoint: {redis_endpoint}")
		vector_store = RedisVectorStore(index_name=index_name, index_prefix=index_name,
										redis_url=redis_endpoint,
										metadata_fields=metadata_fields, overwrite=False)
		logger.info("redis vector store loaded")
		return vector_store


	def load_index(self, index_name, metadata_fields = [], with_llm = True):
		return VectorStoreIndex.from_vector_store(vector_store=self.get_vector_store(index_name, metadata_fields), service_context=self.service_context(with_llm))



