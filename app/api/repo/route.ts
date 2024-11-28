import { NextResponse } from "next/server";
import { getEnvVariables } from "../utils";

export async function GET() {
	try {

		const { url, token } = getEnvVariables()
		const result = await fetch(`${url}/list_repos`, {
			method: 'GET',
			headers: {
				"Authorization": token,
			}
		})

		if (!result.ok) {
			throw new Error(await result.text())
		}

		const { repositories } = await result.json()

		return NextResponse.json({ result: repositories }, { status: 200 })
	} catch (err) {
		console.error(err)
        return NextResponse.json((err as Error).message, { status: 400 })
	}
}

// export async function POST(request: NextRequest) {
	
// 	const repo_url = request.nextUrl.searchParams.get('url');
	
// 	try {

// 		if (!repo_url) {
// 			throw new Error("URL parameter is missing");
// 		}
		
// 		const { url, token } = getEnvVariables();

// 		const result = await fetch(`${url}/process_repo`, {
// 			method: 'POST',
// 			body: JSON.stringify({ repo_url, ignore: ["./.github", "./sbin", "./.git", "./deps", "./bin", "./build"] }),
// 			headers: {
// 				"Authorization": token,
// 				'Content-Type': 'application/json'
// 			}
// 		});

// 		if (!result.ok) {
// 			throw new Error(await result.text());
// 		}

// 		return NextResponse.json({ message: "success" }, { status: 200 });
// 	} catch (err) {
// 		console.error(err)
//      return NextResponse.json((err as Error).message, { status: 400 });
// 	}
// }
