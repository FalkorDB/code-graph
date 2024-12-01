import { getEnvVariables } from "@/app/api/utils";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest, { params }: { params: Promise<{ graph: string, node: string }> }) {

    const p = await params;

    const repo = p.graph;
    const src = Number(p.node);
    const dest = Number(request.nextUrl.searchParams.get('targetId'))

    try {

        if (!dest) {
            throw new Error("targetId is required");
        }

        const { url, token } = getEnvVariables()

        const result = await fetch(`${url}/find_paths`, {
            method: 'POST',
            headers: {
                "Authorization": token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                repo,
                src,
                dest
            }),
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