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
    let schema: any = await graphSchema(graph, graphId, client);

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
    return desc;
}

export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {    
    const graph_id = params.graph;
    let query = request.nextUrl.searchParams.get("q");
    // const type = request.nextUrl.searchParams.get("type");
    
    //-------------------------------------------------------------------------
    // connect to graph
    //-------------------------------------------------------------------------

    // hard coded graph id
    const client = createClient({
        url: process.env.FALKORDB_URL || 'redis://localhost:6379',
    });    
    await client.connect();

    const graph = new Graph(client, graph_id);
    let graph_schema = await GraphSchemaToPrompt(graph, graph_id, client);

    // let prompt: string = `You are a Cypher expert, with access to the following graph:\n
    // ${graph_schema}\n
    // The graph represents a Python code base.
    // Please generate a Cypher query which will answer the following question:\n
    // Which Function is being called often?
    // Your response should contain only the cypher query.`;

    let prompt: string = `You are a Cypher expert, with access to the following graph:\n
    ${graph_schema}\n
    The graph represents a Python code base.
    Please generate a Cypher query which will answer the following question:\n
    ${query}\n
    Your response should contain only the cypher query.`;
    
    const openai = new OpenAI();
    const completion = await openai.chat.completions.create({
        messages: [{ role: "system", content: prompt }],
        model: "gpt-3.5-turbo",
    });

    const output_text = completion.choices[0]['message']['content'];
    
    query = output_text;
    console.log(`query: ${query}\n`);

    if(!query) {
        return NextResponse.json({ result: "No query generated" }, { status: 500 });
    }
    
    let result   = await graph.query(query);
    let response = JSON.stringify(result.data);

    return NextResponse.json({ result: response }, { status: 200 });
}