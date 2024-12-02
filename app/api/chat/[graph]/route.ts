import { NextRequest, NextResponse } from "next/server"
import { getEnvVariables } from "../../utils"


export async function POST(request: NextRequest, { params }: { params: Promise<{ graph: string }> }) {

    const repo = (await params).graph
    const msg = request.nextUrl.searchParams.get('msg')

    try {

        if (!msg) {
            throw new Error("Message parameter is required")
        }

        const { url, token } = getEnvVariables()

        const result = await fetch(`${url}/chat`, {
            method: 'POST',
            body: JSON.stringify({ repo, msg }),
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