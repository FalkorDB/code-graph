import { NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const graphName = params.graph
    const msg = request.nextUrl.searchParams.get('msg')

    try {
        const result = await fetch(`http://localhost:5000/chat`, {
            method: 'POST',
            body: JSON.stringify({ repo: graphName, msg}),
            headers: {
                "Content-Type": 'application/json'
            }
        })

        if (!result.ok) {
            throw new Error(await result.text())
        }

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        return NextResponse.json({ message: (err as Error).message }, { status: 400 })
    }
}