import { NextRequest, NextResponse } from "next/server";
import { getEnvVariables } from "@/app/api/utils";

export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const repo = params.graph;
    const node_ids = (await request.json()).nodeIds.map((id: string) => Number(id));

    try {

        const { url, token } = getEnvVariables();

        if (node_ids.length === 0) {
            throw new Error("nodeIds is required");
        }
        
        const result = await fetch(`${url}/get_neighbors`, {
            method: 'POST',
            body: JSON.stringify({ node_ids, repo }),
            headers: {
                "Content-Type": 'application/json',
                "Authorization": token,
            }
            cache: 'no-store'
        })

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        console.error(err)
        return NextResponse.json((err as Error).message, { status: 400 })
    }
}
