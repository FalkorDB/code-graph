import { NextRequest, NextResponse } from "next/server"

export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {

    const graphName = params.graph

    try {
        const result = await fetch(`${process.env.BACKEND_URL}/graph_entities?repo=${graphName}`, {
            method: 'GET',
            headers: {
                "Authorization": process.env.SECRET_TOKEN!,
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

export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const prefix = request.nextUrl.searchParams.get('prefix')!

    try {
        if (!prefix) {
            throw new Error("Prefix is required")
        }

        const result = await fetch(`${process.env.BACKEND_URL}/auto_complete`, {
            method: 'POST',
            body: JSON.stringify({ repo: params.graph, prefix }),
            headers: {
                "Authorization": process.env.SECRET_TOKEN!,
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