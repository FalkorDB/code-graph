import { NextRequest, NextResponse } from "next/server";
import { getEnvVariables } from "@/app/api/utils";

export async function GET(request: NextRequest, { params }: { params: Promise<{ graph: string }> }) {

    const repo = (await params).graph

    try {

        const { url, token } = getEnvVariables();

        const result = await fetch(`${url}/repo_info`, {
            method: 'POST',
            body: JSON.stringify({ repo }),
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