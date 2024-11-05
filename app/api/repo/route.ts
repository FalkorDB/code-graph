import { NextRequest, NextResponse } from "next/server";

export async function GET() {
	try {
		const result = await fetch(`http://127.0.0.1:5000/list_repos`, {
			method: 'GET',
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

export async function POST(request: NextRequest) {

	const url = request.nextUrl.searchParams.get('url');
	
	try {
		const result = await fetch(`http://127.0.0.1:5000/process_repo`, {
			method: 'POST',
			body: JSON.stringify({ repo_url: url, ignore: ["./.github", "./sbin", "./.git", "./deps", "./bin", "./build"] }),
			headers: {
				'Content-Type': 'application/json'
			}
		})

		if (!result.ok) {
			throw new Error(await result.text())
		}

		return NextResponse.json({ message: "success" }, { status: 200 })
	} catch (err) {
		return NextResponse.json({ message: (err as Error).message }, { status: 400 })
	}
}