import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest, { params }: { params: { graph: string, node: string } }) {

    const nodeId = params.node;
    const graphId = params.graph;
    const targetId = request.nextUrl.searchParams.get('targetId')

    try {

        const result = await fetch(`${process.env.BACKEND_URL}/find_paths`, {
            method: 'POST',
            headers: {
                "Authorization": process.env.SECRET_TOKEN!,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                repo: graphId,
                src: Number(nodeId),
                dest: Number(targetId!)
            }),
            cache: 'no-store'
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