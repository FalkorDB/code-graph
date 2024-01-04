import os from 'os';
import fs from 'fs';
import path from 'path';
import simpleGit from 'simple-git';
import Parser from 'web-tree-sitter';
import { NextRequest, NextResponse } from "next/server";
import { Graph, RedisClientType, RedisDefaultModules, createClient } from 'falkordb';

// const client = createClient();
// client.connect()

//-----------------------------------------------------------------------------
// Tree-Sitter queries
//-----------------------------------------------------------------------------

let parser: Parser;

// class definition tree-sitter query
// responsible for matching class definition, in addition to extracting the class name
let class_definition_query: Parser.Query;

// function definition tree-sitter query
// responsible for matching function definition, in addition to extracting the function name
let function_definition_query: Parser.Query;

// function call tree-sitter query
// responsible for matching function calls, in addition to extracting the callee function name
let function_call_query: Parser.Query;

// Process Python file (Module)
function processPythonSource(source_file: string) {
	// read file
	fs.readFile(source_file, 'utf8', function (err: any, source: string) {
		if (err) {
			return console.log(err);
		}

		// Construct an AST from source
		const tree = parser.parse(source);
		
		// match all Class definitions
		let class_matches = class_definition_query.matches(tree.rootNode);

		// Iterate over each matched Class
		for (let class_match of class_matches) {			
			processClassDeclaration(source_file, class_match);
		}
	});
}

// Process Class declaration
function processClassDeclaration(source_file: string, match: Parser.QueryMatch) {
	let class_node = match.captures[0].node;
	let class_name = match.captures[1].node.text;
	console.log("Class node: " + class_node);
	console.log("Class name: " + class_name);

	// Match all function definition within the current class
	let function_matches = function_definition_query.matches(class_node);
	for (let function_match of function_matches) {	
		processFunctionDeclaration(source_file, function_match);
	}
}

// Process function declaration
function processFunctionDeclaration(source_file: string, match: Parser.QueryMatch) {
	let function_node = match.captures[0].node;
	let function_name = match.captures[1].node.text;
	//console.log("Function definition Node: " + function_node);
	console.log("Function name: " + function_name);

	// Match all function calls within the current function
	let function_call_matches = function_call_query.matches(function_node);

	for (let function_call of function_call_matches) {
		let callee = function_call.captures[0].node.text;
		console.log(function_name + " calls: " + callee);
	}
}

export async function POST(request: NextRequest) {
	// Initialize Tree-Sitter parser
	await Parser.init({
		locateFile(scriptName: string, scriptDirectory: string) {
			return scriptName;
		},
	});

	parser = new Parser();
	const Python = await Parser.Language.load('tree-sitter-python.wasm');

	parser.setLanguage(Python);

	//-------------------------------------------------------------------------
	// Tree-Sitter AST queries
	//-------------------------------------------------------------------------
	
	function_call_query 	  = Python.query(`((call function: (identifier) @function-name))`);
	class_definition_query    = Python.query(`(class_definition name: (identifier) @class-name) @class-definition`);
	function_definition_query = Python.query(`(function_definition name: (identifier) @function-name) @function-definition`);

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
			if (file_stat.isDirectory()) { walk(file_path); }
			else if (file.endsWith(".py")) { source_files.push(file_path); }
		}
	}
	walk(repo_root);
	
	//--------------------------------------------------------------------------
	// process each source file
	//--------------------------------------------------------------------------

	for (let source_file of source_files) {
		console.log("Processing file: " + source_file);
		processPythonSource(source_file);
	}

	return NextResponse.json({ message: "in progress..." }, { status: 201 })
}