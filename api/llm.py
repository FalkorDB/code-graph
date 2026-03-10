import os
import logging

from graphrag_sdk.models.litellm import LiteModel
from graphrag_sdk import (
    Ontology,
    Entity,
    Relation,
    Attribute,
    AttributeType,
    KnowledgeGraph,
    KnowledgeGraphModelConfig
)

from .prompts import (CYPHER_GEN_SYSTEM,
                     CYPHER_GEN_PROMPT,
                     GRAPH_QA_SYSTEM,
                     GRAPH_QA_PROMPT,
                    )


# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(filename)s - %(asctime)s - %(levelname)s - %(message)s')

def _define_ontology() -> Ontology:
    # Build ontology:
    ontology = Ontology()

    # Entities:
    # 1. File
    # 2. Class
    # 3. Function
    # 4. Struct (TODO: Add struct)

    # Relations:
    # File     - DEFINES -> Class
    # File     - DEFINES -> Function
    # Class    - DEFINES -> Class
    # Class    - DEFINES -> Function
    # Function - DEFINES -> Function
    # Class    - CALLS -> Function
    # Function - CALLS -> Function

    # TODO: auto generate ontology
    #"call db.labels()"
    #"call db.relationshiptypes()"
    #"match (n: File) return keys(n) limit 1"
    #"match (n: File) return n limit 1"
    #"match ()-[e: {}]->() return e limit 1

    # Function:
    #   name
    #   path
    #   src_start
    #   src_end
    #   args "[[cls, Unknown]]"
    #   src

    function = Entity(
            label="Function",
            attributes=[
                Attribute(
                    name="name",
                    attr_type=AttributeType.STRING,
                    required=True,
                    unique=True,
                ),
                Attribute(
                    name="path",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src_start",
                    attr_type=AttributeType.NUMBER,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src_end",
                    attr_type=AttributeType.NUMBER,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="args",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
            ]
        )

    # File:
    #   name
    #   ext
    #   path
    file = Entity(
            label="File",
            attributes=[
                    Attribute(
                    name="name",
                    attr_type=AttributeType.STRING,
                    required=True,
                    unique=True,
                ),
                    Attribute(
                        name="path",
                        attr_type=AttributeType.STRING,
                        required=False,
                        unique=False,
                    ),
                    Attribute(
                        name="ext",
                        attr_type=AttributeType.STRING,
                        required=False,
                        unique=False,
                    )
            ]
        )

    # Class:
    #   name
    #   path
    #   src_start
    #   src_end
    #   doc

    cls = Entity(
            label="Class",
            attributes=[
                Attribute(
                    name="name",
                    attr_type=AttributeType.STRING,
                    required=True,
                    unique=True,
                ),
                Attribute(
                    name="path",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src_start",
                    attr_type=AttributeType.NUMBER,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src_end",
                    attr_type=AttributeType.NUMBER,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="doc",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
            ]
        )
    
    interface = Entity(
            label="Interface",
            attributes=[
                Attribute(
                    name="name",
                    attr_type=AttributeType.STRING,
                    required=True,
                    unique=True,
                ),
                Attribute(
                    name="path",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src_start",
                    attr_type=AttributeType.NUMBER,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="src_end",
                    attr_type=AttributeType.NUMBER,
                    required=False,
                    unique=False,
                ),
                Attribute(
                    name="doc",
                    attr_type=AttributeType.STRING,
                    required=False,
                    unique=False,
                ),
            ]
        )

    ontology.add_entity(cls)
    ontology.add_entity(file)
    ontology.add_entity(function)
    ontology.add_entity(interface)

    # Relations:
    # File     - DEFINES -> Class
    # File     - DEFINES -> Function
    # Class    - DEFINES -> Class
    # Class    - DEFINES -> Function
    # Function - DEFINES -> Function
    # Class    - CALLS -> Function
    # Function - CALLS -> Function

    ontology.add_relation(Relation("CALLS",   "Class",    "Function"))
    ontology.add_relation(Relation("CALLS",   "Function", "Function"))
    ontology.add_relation(Relation("DEFINES", "File",     "Class"))
    ontology.add_relation(Relation("DEFINES", "File",     "Function"))
    ontology.add_relation(Relation("DEFINES", "Class",    "Class"))
    ontology.add_relation(Relation("EXTENDS", "Class",    "Class"))
    ontology.add_relation(Relation("IMPLEMENTS", "Class",    "Interface"))
    ontology.add_relation(Relation("DEFINES", "Class",    "Function"))
    ontology.add_relation(Relation("DEFINES", "Function", "Function"))

    return ontology

# Global ontology
ontology = _define_ontology()

def _create_kg_agent(repo_name: str):
    model_name = os.getenv('MODEL_NAME', 'gemini/gemini-2.0-flash')

    model = LiteModel(model_name)

    #ontology = _define_ontology()
    code_graph_kg = KnowledgeGraph(
        name=repo_name,
        ontology=ontology,
        model_config=KnowledgeGraphModelConfig.with_model(model),
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=os.getenv('FALKORDB_PORT', 6379),
        username=os.getenv('FALKORDB_USERNAME', None),
        password=os.getenv('FALKORDB_PASSWORD', None),
        cypher_system_instruction=CYPHER_GEN_SYSTEM,
        qa_system_instruction=GRAPH_QA_SYSTEM,
        cypher_gen_prompt=CYPHER_GEN_PROMPT,
        qa_prompt=GRAPH_QA_PROMPT,
    )

    return code_graph_kg.chat_session()

def ask(repo_name: str, question: str) -> str:
    chat = _create_kg_agent(repo_name)

    logging.debug(f"Question: {question}")
    print(f"Question: {question}")
    response = chat.send_message(question)
    logging.debug(f"Response: {response}")
    print(f"Response: {response['response']}")
    return response['response']