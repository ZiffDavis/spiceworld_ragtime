import os
import json
import warnings

from pydantic import BaseModel
from utils.tafi_vector_stores import *
from llama_index.core import Document


class TafiIndexer:
	def __init__(self, persist_dir = None):
		self.vector_store = TafiSimpleVectorStore(persist_dir = persist_dir)
		self.persist_dir = persist_dir

	def get_index(self, index_id):
		index = self.vector_store.load_index(index_id = index_id, with_llm = False)
		return index

	def query(self, index_name = None, index = None, query_string = None):
		if index==None and index_name!=None:
			index = self.vector_store.load_index(index_name, with_llm = False)
		query_engine = index.as_retriever(similarity_top_k=2)
		response = query_engine.retrieve(query_string)
		response = sorted(response, key = lambda x:x.score, reverse=True)
		return response

	def add_to_index(self, docs = None, index = None, index_name = None, with_llm = False):
		if index == None and index_name!=None:
			self.vector_store.add_to_index(docs = docs, index_name = index_name, with_llm = with_llm)
		else:
			self.vector_store.add_to_index(docs = docs, index = index, with_llm = with_llm)

	def index_from_docs(self, docs = None, index_name = None, with_llm = False):
		index = self.vector_store.index_from_docs(docs = docs, index_name = index_name, with_llm = with_llm)
		index.set_index_id(index_name)
		index.storage_context.persist(persist_dir=self.persist_dir)
		return index


