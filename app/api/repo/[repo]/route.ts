import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { graph_id: string } }) {

    const graph_id = params.graph_id;
    const query = request.nextUrl.searchParams.get("q");
    // const type = request.nextUrl.searchParams.get("type");

    return NextResponse.json({ result: "respose to query: " + query }, { status: 200 })
}