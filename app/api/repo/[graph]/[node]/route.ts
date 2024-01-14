import { Graph, createClient } from "falkordb";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph: string, node: string } }) {
    
    const nodeId  = parseInt(params.node);
    const graphId = params.graph;

    const client = createClient({
		url: process.env.FALKORDB_URL || 'redis://localhost:6379',
	});
	await client.connect();

    const graph = new Graph(client, graphId);

    // Get node's neighbors    
    const q_params = {nodeId: nodeId};
    const query    = `MATCH (src)-[e]-(n)
                      WHERE ID(src) = $nodeId
                      RETURN collect(distinct n) as nodes, collect(e) as edges`;

    console.log(`q_params.nodeId: ${q_params.nodeId}`);

    let res: any = await graph.query(query, { params: q_params });
    let nodes = res.data[0]['nodes'];
    let edges = res.data[0]['edges'];

    nodes.forEach((node: any) => { delete node.src_embeddings});

    return NextResponse.json({ id: graphId, nodes: nodes, edges: edges }, { status: 200 })
}