import os from 'os';
import path from 'path';
import git from 'isomorphic-git';
import http from 'isomorphic-git/http/node';
import Parser from 'web-tree-sitter';

import { promises as fs } from 'fs';
import { Language, SyntaxNode } from 'web-tree-sitter';
import { NextRequest, NextResponse } from "next/server";
import { Graph, RedisClientType, RedisDefaultModules, createClient } from 'falkordb';
import { RESPOSITORIES } from './repositories';

const GraphOps = require('./graph_ops');
const LIMITED_MODE = process.env.NEXT_PUBLIC_MODE?.toLowerCase() === 'limited';

//-----------------------------------------------------------------------------
// Tree-Sitter queries
//-----------------------------------------------------------------------------

let parser: Parser;
let Python: Language;

// class definition tree-sitter query
// responsible for matching class definition, in addition to extracting the class name
let class_definition_query: Parser.Query;

// function definition tree-sitter query
// responsible for matching function definition, in addition to extracting the function name
let function_definition_query: Parser.Query;

// function call tree-sitter query
// responsible for matching function calls, in addition to extracting the callee function name
let function_call_query: Parser.Query;

// function call tree-sitter query
// responsible for matching function calls of type self.f()
// in addition to extracting the callee function name
let function_attr_call_query: Parser.Query;

// identifier tree-sitter query
// responsible for matching Identifier nodes
let identifier_query: Parser.Query;

// Process Class declaration
async function processClassDeclaration
	(
		source_file: string,
		graph: Graph,
		match: Parser.QueryMatch
	) {
	let class_node = match.captures[0].node;
	let class_name = match.captures[1].node.text;
	let class_src_end = class_node.endPosition.row;
	let class_src_start = class_node.startPosition.row;

	// Create Class node
	await GraphOps.create_class(source_file, graph, class_name, class_src_start, class_src_end);
}

// Process function declaration
async function processFunctionDeclaration
	(
		source_file: string,
		graph: Graph,
		match: Parser.QueryMatch
	) {
	let function_node = match.captures[0].node;
	let function_name = match.captures[1].node.text;
	let function_args = match.captures[2].node;

	//-------------------------------------------------------------------------
	// Determine function parent
	//-------------------------------------------------------------------------

	let parent: any = function_node.parent;

	while (parent != null && parent.type != 'class_definition') {
		parent = parent.parent;
	}

	if (parent == null) {
		// function isn't part of a Class
		// this is a Module level function
		const file_components = source_file.split("/");
		parent = file_components[file_components.length - 1];
	} else {
		let identifier_matches = identifier_query.matches(parent)[0].captures;
		const identifierNode = identifier_matches[0].node;
		parent = identifierNode.text;
	}

	//-------------------------------------------------------------------------
	// Extract function args
	//-------------------------------------------------------------------------

	let args: string[] = [];
	for (let i = 0; i < function_args.namedChildCount; i++) {
		let child_node: SyntaxNode = function_args.namedChild(i) as SyntaxNode;
		// if parameter is an identifier e.g. f(a)
		// then simply 
		if (child_node.type == 'identifier') {
			args.push(child_node.text);
		} else {
			let identifier_matches = identifier_query.matches(child_node)
			if (identifier_matches.length == 0) {
				console.log("Investigate!");
				continue;
			}
			let captures = identifier_matches[0].captures;
			const identifierNode = captures[0].node;
			args.push(identifierNode.text);
		}
	}

	let src = function_node.text;
	let function_src_end = function_node.endPosition.row;
	let function_src_start = function_node.startPosition.row;

	// Create Function node
	await GraphOps.create_function(source_file, graph, function_name, parent, args,
		function_src_start, function_src_end, src);
}

// Process function call
async function processFunctionCall
	(
		source_file: string,
		graph: Graph,
		caller: string,
		caller_src_start: number,
		caller_src_end: number,
		match: Parser.QueryMatch
	) {
	let call = match.captures[0].node;	   // caller
	let callee = match.captures[1].node.text;  // called function
	let call_src_end = call.endPosition.row;         // call begins on this line number
	let call_src_start = call.startPosition.row;       // call ends on this line number

	// Create Function call edge
	await GraphOps.create_function_call(source_file, graph, caller, callee,
		caller_src_start, caller_src_end, call_src_start, call_src_end);
}

// Process first pass
// Introduces:
// 1. Modules
// 2. Class declarations
// 3. Function declarations
async function processFirstPass
	(
		source_files: string[],
		graph: Graph
	) {
	for (let source_file of source_files) {
		console.log("Processing file: " + source_file);

		await GraphOps.create_module(source_file, graph);

		const src = await fs.readFile(source_file, 'utf8');

		// Construct an AST from src
		const tree = parser.parse(src);

		// Match all Class definitions
		let class_matches = class_definition_query.matches(tree.rootNode);

		// Iterate over each matched Class
		for (let class_match of class_matches) {
			await processClassDeclaration(source_file, graph, class_match);
		}

		// Match all function definition within the current class
		let function_matches = function_definition_query.matches(tree.rootNode);
		for (let function_match of function_matches) {
			await processFunctionDeclaration(source_file, graph, function_match);
		}
	}
}

// Process second pass
// Introduces:
// 1. Function calls
async function processSecondPass
	(
		source_files: string[],
		graph: Graph
	) {
	// for each source file
	for (let source_file of source_files) {
		const src = await fs.readFile(source_file, 'utf8');

		// Construct an AST from src
		const tree = parser.parse(src);

		// Match all Function definitions
		let function_matches = function_definition_query.matches(tree.rootNode);

		// Iterate over each matched Function
		for (let function_match of function_matches) {
			let function_node = function_match.captures[0].node;
			let function_name = function_match.captures[1].node.text;
			let function_src_start = function_node.startPosition.row;
			let function_src_end = function_node.endPosition.row;

			// Match all function calls: `f()` within the current function
			let function_call_matches = function_call_query.matches(function_node);
			for (let function_call_match of function_call_matches) {
				await processFunctionCall(source_file, graph, function_name,
					function_src_start, function_src_end, function_call_match);
			}

			// Match all function calls: `Obj.foo()` within the current function
			function_call_matches = function_attr_call_query.matches(function_node);
			for (let function_call_match of function_call_matches) {
				await processFunctionCall(source_file, graph, function_name,
					function_src_start, function_src_end, function_call_match);
			}
		}
	}
}

async function BuildGraph
	(
		client: any,
		commit_hash: string,
		graphId: string,
		graph: Graph,
		repo_root: string
	) {
	console.log("BuildGraph");

	// Initialize Tree-Sitter
	await InitializeTreeSitter();

	// Create graph indicies
	GraphOps.create_indices(graph);

	//--------------------------------------------------------------------------
	// collect all source files in repo
	//--------------------------------------------------------------------------

	let source_files: string[] = [];
	let walk = async function (dir: string) {
		let files = await fs.readdir(dir);
		for (let file of files) {
			let file_path = path.join(dir, file);
			let file_stat = await fs.stat(file_path);
			if (file_stat.isDirectory()) { await walk(file_path); }
			else if (file.endsWith(".py")) { source_files.push(file_path); }
		}
	}
	await walk(repo_root);

	//--------------------------------------------------------------------------
	// process each source file
	//--------------------------------------------------------------------------

	// first pass, declarations only.
	await processFirstPass(source_files, graph);

	// second pass calls.
	await processSecondPass(source_files, graph);

	// set graph expiry, expire in 24 hours
	await client.expire(graphId, 86400);

	// create schema graph
	await GraphOps.graphCreateSchema(graph, graphId, client);
}

async function InitializeTreeSitter() {
	// Initialize Tree-Sitter parser
	await Parser.init({
		locateFile(scriptName: string, scriptDirectory: string) {
			return path.join(process.cwd(), 'app/parsers', scriptName);
		},
	});

	parser = new Parser();
	Python = await Parser.Language.load(path.join(process.cwd(), 'app/parsers/tree-sitter-python.wasm'));

	parser.setLanguage(Python);

	//-------------------------------------------------------------------------
	// Tree-Sitter AST queries
	//-------------------------------------------------------------------------

	identifier_query = Python.query(`((identifier) @identifier)`);
	function_call_query = Python.query(`((call function: (identifier) @function-name) @function-call)`);
	function_attr_call_query = Python.query(`((call function: (attribute object: (identifier) attribute: (identifier) @function-name )) @function-call)`);
	class_definition_query = Python.query(`(class_definition name: (identifier) @class-name) @class-definition`);
	function_definition_query = Python.query(`((function_definition name: (identifier) @function-name parameters: (parameters) @parameters) @function-definition)`);
}

export async function POST(request: NextRequest) {


	const body = await request.json();
	const url = body.url;
	if (!url) {
		return NextResponse.json({ medssage: 'URL not provided' }, { status: 400 })
	}
	if (LIMITED_MODE && !RESPOSITORIES.includes(url)) {
		return NextResponse.json({ medssage: 'Repository not supported' }, { status: 401 })
	}

	const urlParts = url.split('/');
	if (urlParts.length < 2) {
		return NextResponse.json({ medssage: 'Invalid URL' }, { status: 400 })
	}
	const organization = urlParts[urlParts.length - 2];
	const repo = urlParts[urlParts.length - 1];

	//-------------------------------------------------------------------------
	// Connect to FalkorDB
	//-------------------------------------------------------------------------
	const client = createClient({
		url: process.env.FALKORDB_URL || 'redis://localhost:6379',
	});
	await client.connect();

	// Download Github Repo into a temporary folder
	// Create temporary folder

	const tmp_dir = os.tmpdir();


	//--------------------------------------------------------------------------
	// process repo
	//--------------------------------------------------------------------------

	let repo_root = path.join(tmp_dir, repo);

	// check if repo was already cloned
	try {
		await fs.stat(repo_root)
	} catch (error) {
		//---------------------------------------------------------------------
		// clone repo into temporary folder
		//---------------------------------------------------------------------
		try {
			await git.clone({ fs, http, dir: repo_root, url, depth: 1 })
			console.log("Cloned repo");
		} catch (error) {
			console.error(error);
			return NextResponse.json({ medssage: 'Repository not found' }, { status: 404 })
		}
	}

	// latest git commit
	let commits = await git.log({ fs, gitdir: path.join(repo_root, '.git'), depth: 1, ref: 'HEAD' });
	let commit_hash: string = commits[0].oid;

	const graphId = `${organization}-${repo}-${commit_hash}`;
	const graph = new Graph(client, graphId);

	let graph_exists = await client.exists(graphId);
	if (!graph_exists) {
		await BuildGraph(client, commit_hash, graphId, graph, repo_root);
	} else {
		// reset graph expiry
		await client.expire(graphId, 86400);
	}

	let code_graph = await GraphOps.projectGraph(graph, 100);

	return NextResponse.json({ id: graphId, nodes: code_graph.nodes, edges: code_graph.edges }, { status: 201 })
}