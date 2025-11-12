import { NextResponse } from "next/server";

import { NextRequest } from "next/server";
import { getEnvVariables } from "../../utils";

export async function GET(request: NextRequest) {

    const id = request.nextUrl.searchParams.get('id');

    try {

        if (!id) throw new Error("Missing id parameter");

        const { url, token } = getEnvVariables();

        const result = await fetch(`${url}/get_analyze_progress?id=${id}`, {
            headers: {
                "Authorization": token,
                "Content-Type": 'application/json'
            },
            cache: 'no-store'
        });

        if (!result.ok) throw new Error(await result.text());

        const json = await result.json();

        return NextResponse.json(json, { status: 200 });

    } catch (error) {
        console.error(error);
        return NextResponse.json({ error: (error as Error).message }, { status: 500 });
    }

}