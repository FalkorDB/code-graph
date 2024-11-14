import { NextRequest, NextResponse } from "next/server";

export async function GET() {
	try {
		const result = await fetch(`${process.env.BACKEND_URL}/list_repos`, {
			method: 'GET',
			headers: {
				"Authorization": process.env.SECRET_TOKEN!,
			}
		})

		if (!result.ok) {
			throw new Error(await result.text())
		}

		const { repositories } = await result.json()

		return NextResponse.json({ result: repositories }, { status: 200 })
	} catch (err) {
		return NextResponse.json({ message: (err as Error).message }, { status: 400 })
	}
}

// export async function POST(request: NextRequest) {

// 	const url = request.nextUrl.searchParams.get('url');

// 	try {
// 		const result = await fetch(`${process.env.BEAKEND_URL}/process_repo`, {
// 			method: 'POST',
// 			body: JSON.stringify({ repo_url: url, ignore: ["./.github", "./sbin", "./.git", "./deps", "./bin", "./build"] }),
// 			headers: {
// 				"Authorization": process.env.SECRET_TOKEN!,
// 				'Content-Type': 'application/json'
// 			}
// 		})

// 		if (!result.ok) {
// 			throw new Error(await result.text())
// 		}

// 		return NextResponse.json({ message: "success" }, { status: 200 })
// 	} catch (err) {
// 		return NextResponse.json({ message: (err as Error).message }, { status: 400 })
// 	}
// }
