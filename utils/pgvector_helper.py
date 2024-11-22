from loguru import logger
import os
from llama_index.indices.vector_store import VectorStoreIndex
from llama_index.embeddings import LangchainEmbedding

from llama_index import Document, StorageContext, ServiceContext, get_response_synthesizer
#from langchain.llms.vertexai import VertexAI
from langchain_community.llms import VertexAI
#from langchain.embeddings import HuggingFaceEmbeddings 
from langchain_community.embeddings import HuggingFaceEmbeddings
from llama_index.vector_stores import PGVectorStore
from llama_index.node_parser import SimpleNodeParser
import psycopg2


class PGVectorHelper:
  def __init__(self):
    self.indices = {}
  def get_vector_store(self, table_name):
    os.environ["PGVECTOR_VECTOR_SIZE"] = "384"
    vector_store = PGVectorStore.from_params(
      database=os.environ["PG_DB_DBASE"],
      host=os.environ["PG_DB_HOST"],
      password=os.environ["PG_DB_PASS"],
      port=5432,
      user=os.environ["PG_DB_USER"],
      table_name=table_name,
      embed_dim=384
    )
    return vector_store

  def load_index(self, index_name, metadata_fields=["url"]):
      return VectorStoreIndex.from_vector_store(vector_store=get_vector_store(), service_context=get_service_context())

  def get_node_parser(self):
      return SimpleNodeParser.from_defaults(chunk_size=1024, chunk_overlap=20)

  def get_service_context(self):
      embed_model = self.get_embed_model()
      node_parser = self.get_node_parser()
      service_context = ServiceContext.from_defaults(
          embed_model=embed_model,
          llm=None, #skips intermediary step to external LLM
          node_parser=node_parser

      )
      return service_context

  def get_embed_model(self):
     return LangchainEmbedding(HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2"))
     #return LangchainEmbedding(HuggingFaceEmbeddings(model_name="sangmini/msmarco-cotmae-MiniLM-L12_en-ko-ja"))

  def load_index(self, name): 
    print("loading index")
    return VectorStoreIndex.from_vector_store(vector_store=self.get_vector_store(name), service_context=self.get_service_context())


  def query_index(self, name, query):
    print("querying index")
    if name not in self.indices:
      self.indices["name"] = self.load_index(name)
    index = self.indices["name"]
    query_engine = index.as_retriever(similarity_top_k=5)
    response = query_engine.retrieve(query)
    return response



  def build_index_from_docs(self, docs, table_name):
   
    storage_context = StorageContext.from_defaults(
      vector_store = self.get_vector_store(table_name)
    )
    service_context = self.get_service_context()
    index = VectorStoreIndex.from_documents(docs,
                                                include_embeddings=True,
                                                storage_context=storage_context,
                                                service_context=service_context,
                                                show_progress=True
                                                )
    return index

