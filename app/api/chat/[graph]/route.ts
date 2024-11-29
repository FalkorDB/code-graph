import { NextRequest, NextResponse } from "next/server"


export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const graphName = params.graph
    const msg = request.nextUrl.searchParams.get('msg')

    try {
        const result = await fetch(`${process.env.BACKEND_URL}/chat`, {
            method: 'POST',
            body: JSON.stringify({ repo: graphName, msg }),
            headers: {
                "Authorization": process.env.SECRET_TOKEN!,
                "Content-Type": 'application/json'
            },
            cache: 'no-store'
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