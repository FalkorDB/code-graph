import { NextRequest, NextResponse } from "next/server"
import { getEnvVariables } from "../../utils"

export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {

    const graphName = params.graph

    try {

        const { url, token } = getEnvVariables()

        const result = await fetch(`${url}/graph_entities?repo=${graphName}`, {
            method: 'GET',
            headers: {
                "Authorization": token,
            }
        })

        if (!result.ok) {
            throw new Error(await result.text())
        }

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        console.error(err)
        return NextResponse.json((err as Error).message, { status: 400 })
    }
}

export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const repo = params.graph
    const prefix = request.nextUrl.searchParams.get('prefix')!

    try {

        if (!prefix) {
            throw new Error("Prefix is required")
        }

        const { url, token } = getEnvVariables()

        const result = await fetch(`${url}/auto_complete`, {
            method: 'POST',
            body: JSON.stringify({ repo, prefix }),
            headers: {
                "Authorization": token,
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
        console.error(err)
        return NextResponse.json((err as Error).message, { status: 400 })
    }
}