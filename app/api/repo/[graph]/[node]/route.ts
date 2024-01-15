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
                      RETURN collect(distinct { label:labels(n)[0], id:ID(n), name: n.name } ) as nodes,
                      collect( { src: ID(startNode(e)), id: ID(e), dest: ID(endNode(e)), type: type(e) } ) as edges`;

    let res: any = await graph.query(query, { params: q_params });
    let nodes = res.data[0]['nodes'];
    let edges = res.data[0]['edges'];

    return NextResponse.json({ id: graphId, nodes: nodes, edges: edges }, { status: 200 })
}