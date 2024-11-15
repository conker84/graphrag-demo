# Databricks notebook source
# MAGIC %md
# MAGIC # Create the GraphRAG chatbot with Langchain and Neo4j
# MAGIC
# MAGIC You can test the behaviour of the chatbot with whatever LLM in this example we use OpenAI gpt-4. In order to use it just put your api key inside the property `OPEN_AI_API_KEY` placed in the `.env` file.

# COMMAND ----------

# MAGIC %pip install -q python-dotenv neo4j langchain-openai databricks-agents mlflow mlflow-skinny langchain==0.2.1 langchain_core==0.2.5 langchain_community==0.2.4

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os
from dotenv import load_dotenv
from pathlib import Path
import sys

# COMMAND ----------

# Define the path to the .env file located in the "code" directory
dot_env_path = Path("/model/code/.env")

# Initialize a variable to track if the .env file is loaded
is_env_loaded = None

# Check if the .env file exists at the specified path
if dot_env_path.exists():
    # Print a message indicating the .env file was found
    print(".env file found in code")
    # Load environment variables from the specified .env file (in case it is invoked from a serving endpoint)
    is_env_loaded = load_dotenv(dotenv_path=dot_env_path)
else:
    # Print a message indicating the .env file was not found
    print(".env file not found in code")
    # Load environment variables from a default .env file if the specified one does not exist
    is_env_loaded = load_dotenv()

# Raise an exception if the environment variables were not loaded properly
if not is_env_loaded:
    raise Exception(f"Environment variables not loaded properly from .env file")

# COMMAND ----------

neo4j_url = os.getenv('NEO4J_URL')
neo4j_username = os.getenv('NEO4J_USER')
neo4j_password = os.getenv('NEO4J_PASSWORD')

# COMMAND ----------

# from langchain_databricks import ChatDatabricks
from langchain_openai import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
from langchain.prompts.prompt import PromptTemplate
from langchain_core.runnables import RunnableLambda
import mlflow

# COMMAND ----------

mlflow.langchain.autolog()

# COMMAND ----------

graph = Neo4jGraph(
    url=neo4j_url,
    username=neo4j_username,
    password=neo4j_password
)

# COMMAND ----------

CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["schema", "question"], template=os.getenv('SYSTEM_PROMPT')
)

# COMMAND ----------

llm = ChatOpenAI(
    model="gpt-4",
    temperature=0.2,
    api_key=os.getenv('OPEN_AI_API_KEY'), # if you prefer to pass api key in directly instaed of using env vars
)
# llm = ChatDatabricks(
#     target_uri="databricks",
#     temperature=0.1,
#     # endpoint="databricks-llama-2-70b-chat",
#     endpoint=os.getenv('LLM_MODEL_SERVING_ENDPOINT_NAME')
# )

# COMMAND ----------

# Create a GraphCypherQAChain instance using a language model from Databricks and the Neo4j graph
chain = GraphCypherQAChain.from_llm(
    # Pass the language model
    llm,
    # Pass the Neo4j graph instance
    graph=graph,
    # Enable verbose mode for detailed logging
    verbose=False,
    # Use the predefined Cypher generation prompt template
    cypher_prompt=CYPHER_GENERATION_PROMPT,
    # Allow potentially dangerous requests
    allow_dangerous_requests=True,
    # Validate the generated Cypher queries
    validate_cypher=True
) |  RunnableLambda(lambda x: x["result"]) # The RunnableLambda step is used for properly extracting the result

# COMMAND ----------

# Log the GraphCypherQAChain instance as an MLflow model
mlflow.models.set_model(model=chain)

# COMMAND ----------

# if it's not ran from the Databricks model serving endpoint please run this for debug
if not dot_env_path.exists():
  response = chain.invoke("Can you show potiential attack paths in our network? Return the first five results")
  print(response)
