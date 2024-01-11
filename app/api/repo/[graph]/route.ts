import { Graph, RedisClientType, createClient } from 'falkordb';
import { NextRequest, NextResponse } from "next/server";
import { graphSchema } from "../graph_ops";
import OpenAI from "openai";


// convert a structured graph schema into a string representation
// used in a model prompt
async function GraphSchemaToPrompt(
    graph: Graph,
    graphId: string,
    client: any
) {
    // Retrieve graph schema
    let schema: any = await graphSchema(graphId, client);

    // Build a string description of graph schema
    let desc: string = "The knowladge graph schema is as follows:\n";

    //-------------------------------------------------------------------------
    // Describe labels
    //-------------------------------------------------------------------------

    // list labels
    desc = desc + "The graph contains the following node labels:\n";
    for (const lbl in schema["labels"]) {
        desc = desc + `${lbl}\n`;
    }

    // specify attributes associated with each label
    for (const lbl in schema["labels"]) {
        let node_count = schema["labels"][lbl]['node_count'];
        let attributes = schema["labels"][lbl]['attributes'];
        let attr_count = Object.keys(attributes).length;

        if(attr_count == 0) {
            desc = desc + `the ${lbl} label has ${node_count} nodes and has no attributes\n`;
        } else {
            desc = desc + `the ${lbl} label has ${node_count} nodes and is associated with the following attribute(s):\n`;
            for (const attr in attributes) {
                let type = attributes[attr]['type'];            
                desc = desc + `'${attr}' which is of type ${type}\n`;
            }
        }
    }

    desc = desc + "The graph contains the following relationship types:\n"
    
    //-------------------------------------------------------------------------
    // Describe relationships
    //-------------------------------------------------------------------------

    // list relations
    for (const relation in schema["relations"]) {
        desc = desc + `${relation}\n`;
    }

    // specify attributes associated with each relationship
    for (const relation in schema["relations"]) {
        let connect    = schema["relations"][relation]['connect'];
        let edge_count = schema["relations"][relation]['edge_count'];
        let attributes = schema["relations"][relation]['attributes'];
        let attr_count = Object.keys(attributes).length;

        if(attr_count == 0) {
            desc = desc + `the ${relation} relationship has ${edge_count} edges and has no attributes\n`;
        } else {
            desc = desc + `the ${relation} relationship has ${edge_count} edges and is associated with the following attribute(s):\n`;
            for (const attr in attributes) {
                let type = attributes[attr]['type'];            
                desc = desc + `'${attr}' which is of type ${type}\n`;
            }
        }

        if(connect.length > 0) {
            desc = desc + `the ${relation} relationship connects the following labels:\n`
            for(let i = 0; i < connect.length; i+=2) {
                let src = connect[i];
                let dest = connect[i+1];
                desc = desc + `${src} is connected via ${relation} to ${dest}\n`;
            }
        }
    }

    desc = desc + `This is the end of the knowladge graph schema description.\n`

    //-------------------------------------------------------------------------
    // include graph indices
    //-------------------------------------------------------------------------

    // vector indices
    let query = `CALL db.indexes() YIELD label, properties, types, entitytype`;
    let res = await graph.query(query);
    
    // process indexes
    let indexes: any = res.data;
    if(indexes.length > 0) {
        let index_prompt = "The knowladge graph contains the following indexes:\n"
        for(let i = 0; i < indexes.length; i++) {
            const index = indexes[i];
            const label: string      = index['label'];
            const entityType: string = index['entitytype'];
            const props              = index['properties'];
            const types              = index['types'];

            for(const prop of props) {
                const propTypes: string[] = types[prop];
                for(let j = 0; j < propTypes.length; j++) {
                    const idxType: string = propTypes[j];
                    index_prompt += `${entityType} of type ${label} have a ${idxType} index indexing its ${prop} attribute\n`;
                }
            }
        }
        index_prompt += `This is the end of our indexes list
        To use a Vector index use the following procedure:
        CALL db.idx.vector.queryNodes(<LABEL>, <PROPERTY>, <N>, vecf32(<array_of_vector_elements>)) YIELD node

        The procedure returns up to N nodes that have a <PROPERTY> value which is semanticly close to
        the query vector.

        Here are a few question / answer examples of using the vector index:
        Question: Find 3 functions which have nested loops, return a list of callers
        Your response should be: GENERATE EMBEDDINGS "nested loops" and run the following query:
        CALL db.idx.vector.queryNodes('Function', 'source', 3, vecf32($embedding)) YIELD node MATCH (f)-[:CALLS]->(node) RETURN node.name

        Question: List 5 Classes which contain a function that raise an exception
        Your response should be: GENERATE EMBEDDINGS "raise exception" and run the following:
        CALL db.idx.vector.queryNodes('Function', 'source', 5, vecf32($embedding)) YIELD node MATCH (c:Class)-[:CONTAINS]->(node) RETURN class.name, node.name
    `;

        desc += index_prompt;

    }  

    return desc;
}

// handle instruction from OpenAI
// there are two types of accepted instructions:
// 1. Run query.
// 2. Generate embeddings and run a query.
async function HandleInstruction
(
    instruction: string,
    graph:Graph
) {
    instruction = instruction.trim();
    console.log(`instruction: ${instruction}`);

    if (instruction.startsWith("RUN QUERY")) {
        let query = instruction.substring(instruction.indexOf("RUN QUERY") + "RUN QUERY".length);
        let result = await graph.roQuery(query);
        return result.data;
    } else if (instruction.indexOf("GENERATE EMBEDDINGS") >= 0) {
        // GENERATE EMBEDDINGS <text-to-create-embeddings-for> RUN QUERY followed a CYPHER query.
        let start_idx = instruction.indexOf("GENERATE EMBEDDINGS") + "GENERATE EMBEDDINGS".length;
        let end_idx   = instruction.indexOf("RUN QUERY");
        let text      = instruction.substring(start_idx, end_idx);

        const openai    = new OpenAI();
        const embedding = await openai.embeddings.create({model: "text-embedding-ada-002", input: text});
        const vector    = embedding.data[0].embedding;

        let query  = instruction.substring(instruction.indexOf("RUN QUERY") + "RUN QUERY".length);
        let result = await graph.roQuery(query, {params: {'embedding': vector}});
        return result.data;
    }

    // unknown instruction
    return null;
}

// Chat bot handler
export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {    
    const graph_id = params.graph;
    let query = request.nextUrl.searchParams.get("q");

    //-------------------------------------------------------------------------
    // Connect to graph
    //-------------------------------------------------------------------------

    // hard coded graph id
    const client = createClient({
        url: process.env.FALKORDB_URL || 'redis://localhost:6379',
    });    
    await client.connect();

    const graph = new Graph(client, graph_id);

    //-------------------------------------------------------------------------
    // Construct prompt
    //-------------------------------------------------------------------------

    let graph_schema = await GraphSchemaToPrompt(graph, graph_id, client);

    let prompt: string = `You are a Cypher expert, with access to the following graph:\n
    ${graph_schema}\n
    The graph represents a Python code base.
    Depending on the user question asked you should only respond in one of two ways:
    1. RUN QUERY followed by the CYPHER query to run.
    2. GENERATE EMBEDDINGS <text-to-create-embeddings-for> RUN QUERY followed by the CYPHER query to run.
    Whichever option is more appropriate, option 2 should only be used when
    a semantic search against a Function node src_code attribute is needs to be performed via a CALL db.idx.vector.queryNodes procedure invocation and a relavent vector index exists.
    You are instructed to NOT add any additional information, simply answer with either
    RUN QUERY followed by a CYPHER query
    or
    GENERATE EMBEDDINGS <text-to-create-embeddings-for> RUN QUERY followed a CYPHER query.`;
    
    //-------------------------------------------------------------------------
    // Send prompt to OpenAI
    //-------------------------------------------------------------------------

    const openai = new OpenAI();
    let messages = [
        { role: 'system', content: prompt },
        { role: 'user', content: `Question: ${query}`, name: 'user'},
    ];

    let completion = await openai.chat.completions.create({
        messages: messages,
        model: "gpt-3.5-turbo",
    });

    //-------------------------------------------------------------------------
    // Perform instruction
    //-------------------------------------------------------------------------    

    const instruction = completion.choices[0]['message']['content'];

     let result = await HandleInstruction(instruction, graph);
     if(!result) {
         return NextResponse.json({ result: "No query generated" }, { status: 500 });
     }
     let response = JSON.stringify(result);

    //-------------------------------------------------------------------------
    // Digest response
    //-------------------------------------------------------------------------

    prompt = `This is the user's question: ${query}
    And this is the data we've got from our knowladge graph: ${response}
    Please formulate an answer to the user question based on the data we've got from the knowladge graph`;
    
    messages   = [{ "role": "system", "content": prompt }];
    completion = await openai.chat.completions.create({
        "model":       "gpt-3.5-turbo",
        "messages":    messages,
    });
    const answer = completion.choices[0]['message']['content'];

    console.log(`response: ${answer}`);
    return NextResponse.json({ result: answer }, { status: 200 });
}