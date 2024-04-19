import { FalkorDB, Graph } from "falkordb";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph: string, node: string } }) {
    
    const nodeId  = parseInt(params.node);
    const graphId = params.graph;

    const db = await FalkorDB.connect({url: process.env.FALKORDB_URL || 'falkor://localhost:6379',});
    const graph = db.selectGraph(graphId);

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