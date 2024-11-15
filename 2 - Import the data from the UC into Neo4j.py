# Databricks notebook source
# MAGIC %md
# MAGIC # From Unity Catalog to Neo4j
# MAGIC
# MAGIC In this notebook we'll see how to convert UC's Delta tables into node/relationships stored in Neo4j.
# MAGIC
# MAGIC For structured data, a useful starting point is to leverage the structural dependencies already present in your lakehouse's silver tables; these tables are typically defined with constraints like **foreign keys**. 
# MAGIC
# MAGIC A simple example would be an Entity-Relationship (ER) diagram consisting of two tables, artist and song, and a join table, performs.
# MAGIC
# MAGIC <img src="images/er-model.png">
# MAGIC
# MAGIC The corresponding graph model would be relatively straightforward: two nodes (`Artist` and `Song`) connected by the relationship `PERFORMS`:
# MAGIC
# MAGIC <img src="images/er-to-graph-model.png">
# MAGIC
# MAGIC In this particular scenario, with the Bloodhound dataset, the final graph model will look like the following:
# MAGIC
# MAGIC <img src="https://guides.neo4j.com/sandbox/cybersecurity/img/model.svg">

# COMMAND ----------

# MAGIC %md
# MAGIC ## How to create a Neo4j instance
# MAGIC You can create a free Neo4j Aura instance from [here](https://neo4j.com/product/auradb/).
# MAGIC The free version is just enough for the scope of this demo and once you got the endpoints put them in the `.env` files in the `NEO4J_URL` and `NEO4J_PASSWORD` variables.

# COMMAND ----------

# MAGIC %pip install -q python-dotenv
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./Config

# COMMAND ----------

import os
import pyspark.sql.functions as F
from dotenv import load_dotenv

# COMMAND ----------

load_dotenv()

# COMMAND ----------

# Setting Spark Conf with the Neo4j endpoints
spark.conf.set('neo4j.url', os.getenv('NEO4J_URL'))
spark.conf.set('neo4j.authentication.basic.username', os.getenv('NEO4J_USER'))
spark.conf.set('neo4j.authentication.basic.password', os.getenv('NEO4J_PASSWORD'))
spark.conf.set('neo4j.authentication.type', 'basic')

# COMMAND ----------

# Query to get the list of tables in the specified catalog and database
nodes = (
  spark
    .sql(f'show tables in {catalog_name}.default')
    # Filter the tables to include only those in the node_tables list
    .where(F.col('tableName').isin(list(node_tables)))
    # Select only the tableName column
    .select('tableName')
    # Collect the results into a list of Row objects
    .collect()
)

# COMMAND ----------

for node in nodes:
  # Extract the primary key column name for the current table
  table_pk = ( 
    spark
      .sql(f'describe table extended {catalog_name}.default.`{node.tableName}`')
      .where("col_name like '%_pk'")
      .select(F.regexp_extract_all(F.col('data_type'), F.lit('PRIMARY KEY \\(`(.*)`\\)'), F.lit(1)).getItem(0).alias('pk'))
      .collect()[0]
      .pk
  )
  
  # Read the table data and write it to Neo4j with the appropriate options
  (
    spark.read
      .table(f'{catalog_name}.default.`{node.tableName}`')
      .write
      .mode("overwrite")
      .format("org.neo4j.spark.DataSource")
      .option("labels", node.tableName)
      .option("node.keys", table_pk)
      .option("schema.optimization.node.keys", "UNIQUE")
      .save()
  )

# COMMAND ----------

# Query to get the list of tables in the specified catalog and database
relationships = (
  spark
    .sql(f'show tables in {catalog_name}.default')
    # Filter the tables to include only those in the rel_tables list
    .where(F.col('tableName').isin(list(rel_tables)))
    # Select only the tableName column
    .select('tableName')
    # Collect the results into a list of Row objects
    .collect()
)

# COMMAND ----------

# Define the regular expression pattern for extracting foreign key information
regexpr = F.lit(f'FOREIGN KEY \\(`(.*)`\\) REFERENCES `{catalog_name}`\\.`default`\\.`(.*)` \\(`(.*)`\\)')
datatype_col = F.col('data_type')

# Iterate over each relationship table
for rel in relationships:
  # Extract foreign key information for the current table
  table_fks = ( 
    spark
      .sql(f'describe table extended {catalog_name}.default.`{rel.tableName}`')
      .where("col_name like '%_fk'")
      .select(
        F.regexp_extract_all(datatype_col, regexpr, F.lit(1)).getItem(0).alias('table_col'),
        F.regexp_extract_all(datatype_col, regexpr, F.lit(2)).getItem(0).alias('fk_table_name'),
        F.regexp_extract_all(datatype_col, regexpr, F.lit(3)).getItem(0).alias('fk_table_col')
      )
      .collect()
  )
  
  # Extract the relationship name from the table name
  rel_name = rel.tableName.split("-")[1]
  
  # Initialize variables for source and target labels and keys
  for table_fk in table_fks:
    if table_fk.table_col.startswith('source_'):
      source_label = table_fk.fk_table_name
      source_key = f'{table_fk.table_col}:{table_fk.fk_table_col}'
    else:
      target_label = table_fk.fk_table_name
      target_key = f'{table_fk.table_col}:{table_fk.fk_table_col}'
  
  # Print the relationship details for debugging purposes
  print(f'''
  For table {rel.tableName} we have:
  - source_label: {source_label}
  - source_key: {source_key}
  - target_label: {target_label}
  - target_key: {target_key}
  - relationship name: {rel_name}
  ''')
  
  # Read the relationship table data and write it to Neo4j with the appropriate options
  (
    spark.read
      .table(f'{catalog_name}.default.`{rel.tableName}`')
      .coalesce(1)
      .write
      .mode("overwrite")
      .format("org.neo4j.spark.DataSource")
      .option("relationship", rel_name.upper())
      .option("relationship.save.strategy", "keys")
      .option("relationship.source.labels", source_label)
      .option("relationship.source.save.mode", "Match")
      .option("relationship.source.node.keys", source_key)
      .option("relationship.target.labels", target_label)
      .option("relationship.target.save.mode", "Match")
      .option("relationship.target.node.keys", target_key)
      .save()
  )
