import { Graph, createClient } from "falkordb";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph: string, node: string } }) {
    
    const node    = params.node;
    const graphId = params.graph;

    const client = createClient({
		url: process.env.FALKORDB_URL || 'redis://localhost:6379',
	});
	await client.connect();

    const graph = new Graph(client, graphId);

    // Get node's neighbors
    let res: any = await graph.query(`MATCH ({name:'${node}'})-[e]-(n)
                                      RETURN collect(distinct n) as nodes, collect(e) as edges`);
    let nodes = res.data[0]['nodes'];
    let edges = res.data[0]['edges'];

    return NextResponse.json({ id: graphId, nodes: nodes, edges: edges }, { status: 200 })
}