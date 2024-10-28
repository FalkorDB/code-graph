import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph: string, node: string } }) {

    const nodeId = parseInt(params.node);
    const graphId = params.graph;
    try {

        const result = await fetch(`http://localhost:5000/get_neighbors?repo=${graphId}&node_id=${nodeId}`, {
            method: 'GET',
        })

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        return NextResponse.json({ massage: (err as Error).message }, { status: 400 })
    }
}

export async function POST(request: NextRequest, { params }: { params: { graph: string, node: string } }) {

    const nodeId = params.node;
    const graphId = params.graph;
    const targetId = request.nextUrl.searchParams.get('targetId')
    
    try {

        const result = await fetch(`http://localhost:5000/find_paths`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                repo: graphId,
                src: Number(nodeId),
                dest: Number(targetId!)
            })
        })

        if (!result.ok) {
            throw new Error(await result.text())
        }

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        return NextResponse.json({ massage: (err as Error).message }, { status: 200 })
    }
}