import { Graph, createClient } from "falkordb";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph: string, node: string } }) {

    const graphId = params.graph;
    const node = params.node;


    const client = createClient({
		url: process.env.FALKORDB_URL || 'redis://localhost:6379',
	});
	await client.connect();

    const graph = new Graph(client, graphId);

    // Get the node neighbors, the edges and their properties 
    let nodes = await graph.query(`MATCH ({name:'${node}'})-[]-(n) RETURN n`);
    let edges = await graph.query(`MATCH ({name:'${node}'})-[e]-() RETURN e`);

    return NextResponse.json({ id: graphId, nodes: nodes.data, edges: edges.data }, { status: 200 })
}