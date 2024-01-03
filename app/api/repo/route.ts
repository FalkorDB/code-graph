import { NextRequest, NextResponse } from "next/server";
import { Graph, RedisClientType, RedisDefaultModules, createClient } from 'falkordb';

const client = createClient();
client.connect()

export async function POST(request: NextRequest) {

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

    return NextResponse.json({ message: "in progress..." }, { status: 201 })
}
