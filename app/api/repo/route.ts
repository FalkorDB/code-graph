import { NextRequest, NextResponse } from "next/server";
import { Graph, RedisClientType, RedisDefaultModules, createClient } from 'falkordb';
import Parser from 'web-tree-sitter';
import os from 'os';
import fs from 'fs';
import path from 'path';


//const client = createClient();
//client.connect()

export async function POST(request: NextRequest) {
	// parse source files
	// const Parser = require('tree-sitter');
	//await Parser.init();
	await Parser.init({
		locateFile(scriptName: string, scriptDirectory: string) {
			return scriptName;
		},
	});
	const parser = new Parser();
	console.log("Parser: " + parser);

	const Python = await Parser.Language.load('tree-sitter-python.wasm');
	console.log("Python: " + Python);

	// const Python = require('tree-sitter-python');
	//const JavaScript = require('tree-sitter-javascript');
	// console.log("Python: " + Python);

	//const parser = new Parser();
	parser.setLanguage(Python);

	// Download Github Repo into a temporary folder
	// Create temporary folder


	const tmp_dir = os.tmpdir();
	console.log("Temporary directory: " + tmp_dir);

	// const url = "https://github.com/falkorDB/falkordb-py";

	let body = await request.json();
	let url = body.url;
	console.log("Processing url: " + url);

	//--------------------------------------------------------------------------
	// clone repo into temporary folder
	//--------------------------------------------------------------------------

	const simpleGit = require('simple-git');
	const git = simpleGit({ baseDir: tmp_dir });
	git.clone(url);

	console.log("Cloned repo");

	//--------------------------------------------------------------------------
	// process repo
	//--------------------------------------------------------------------------

	let repo_name = url.split("/").pop();
	let repo_root = path.join(tmp_dir, repo_name);
	console.log("repo_root: " + repo_root);

	//--------------------------------------------------------------------------
	// collect all source files in repo
	//--------------------------------------------------------------------------

	let source_files: string[] = [];
	let walk = function (dir: string) {
		let files = fs.readdirSync(dir);
		for (let file of files) {
			let file_path = path.join(dir, file);
			let file_stat = fs.statSync(file_path);
			if (file_stat.isDirectory()) {
				walk(file_path);
			}
			else {
				if (file.endsWith(".py")) {
					source_files.push(file_path);
				}
			}
		}
	}
	walk(repo_root);

	for (let source_file of source_files) {
		console.log("Processing file: " + source_file);
		// read file
		fs.readFile(source_file, 'utf8', function (err: any, source: string) {
			if (err) {
				return console.log(err);
			}
			const tree = parser.parse(source);
			console.log("Tree: " + tree);
		});
	}

	return NextResponse.json({ message: "in progress..." }, { status: 201 })
}
