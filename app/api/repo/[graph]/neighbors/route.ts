import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const { nodeIds } = await request.json();
    const graphId = params.graph;
    try {

        const result = await fetch(`${process.env.BACKEND_URL}/get_neighbors`, {
            method: 'POST',
            body: JSON.stringify({ node_ids: nodeIds, repo: graphId }),
            headers: {
                "Content-Type": 'application/json',
                "Authorization": process.env.SECRET_TOKEN!,
            }
        })

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        return NextResponse.json({ massage: (err as Error).message }, { status: 400 })
    }
}
