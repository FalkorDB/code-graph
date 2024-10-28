import { NextRequest, NextResponse } from "next/server"

export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {

    const graphName = params.graph

    try {
        const result = await fetch(`http://localhost:5000/graph_entities?repo=${graphName}`, {
            method: 'GET',
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

    const type = request.nextUrl.searchParams.get('type') || "count"
    const graphName = params.graph

    try {
        switch (type) {
            case "commit": {
                const result = await fetch(`http://localhost:5000/list_commits`, {
                    method: 'POST',
                    body: JSON.stringify({ repo: graphName }),
                    headers: {
                        "Content-Type": 'application/json'
                    }
                })

                if (!result.ok) {
                    throw new Error(await result.text())
                }

                const json = await result.json()

                return NextResponse.json({ result: json }, { status: 200 })
            }
            case "autoComplete": {
                const prefix = request.nextUrl.searchParams.get('prefix')!
                const result = await fetch(`http://localhost:5000/auto_complete`, {
                    method: 'POST',
                    body: JSON.stringify({ repo: graphName, prefix}),
                    headers: {
                        "Content-Type": 'application/json'
                    }
                })

                if (!result.ok) {
                    throw new Error(await result.text())
                }

                const json = await result.json()

                return NextResponse.json({ result: json }, { status: 200 })
            }
            default: {
                const result = await fetch(`http://localhost:5000/repo_info`, {
                    method: 'POST',
                    body: JSON.stringify({ repo: graphName }),
                    headers: {
                        "Content-Type": 'application/json'
                    }
                })

                if (!result.ok) {
                    throw new Error(await result.text())
                }

                const json = await result.json()

                return NextResponse.json({ result: json }, { status: 200 })
            }
        }
    } catch (err) {
        return NextResponse.json({ message: (err as Error).message }, { status: 400 })
    }


}