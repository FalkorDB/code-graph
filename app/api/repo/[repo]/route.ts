import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { repo: string } }) {

    const repo = params.repo
    const query = request.nextUrl.searchParams.get("q")
    const type = request.nextUrl.searchParams.get("type")
    
    // const graphID = request.nextUrl.searchParams.get("graph");
    // try {
    //     if (graphID) {
    //         const query = request.nextUrl.searchParams.get("query");
    //         if (!query) {
    //             return NextResponse.json({ message: "Missing query parameter 'q'" }, { status: 400 })
    //         }
    //         const graph = new Graph(client, graphID);
    //         let result = await graph.query(query)
    //         return NextResponse.json({ result: result }, { status: 200 })
    //     } else {

    //         let result = await client.graph.list()
    //         return NextResponse.json({ result: { graphs: result } }, { status: 200 })
    //     }
    // } catch (err: any) {
    //     return NextResponse.json({ message: err.message }, { status: 400 })
    // }

    return NextResponse.json({ repo, query, type }, { status: 200 })
}
