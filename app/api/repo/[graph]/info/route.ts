import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {

    try {
        const result = await fetch(`${process.env.BACKEND_URL}/repo_info`, {
            method: 'POST',
            body: JSON.stringify({ repo: params.graph }),
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