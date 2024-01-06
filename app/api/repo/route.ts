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
// Graph operations
//-----------------------------------------------------------------------------

function create_indices(graph: Graph) {
    console.log("Creating indices");

    //-------------------------------------------------------------------------
    // index "name" attribute
    //-------------------------------------------------------------------------

    console.log("Creating range index on Class.name");
    graph.query("CREATE INDEX FOR (c:Class) ON (c.name)");    

    console.log("Creating range index on Module.name");
    graph.query("CREATE INDEX FOR (m:Module) ON (m.name)");

    console.log("Creating range index on Function.name");
    graph.query("CREATE INDEX FOR (f:Function) ON (f.name)");

    //-------------------------------------------------------------------------
    // index "src_embeddings" attribute
    //-------------------------------------------------------------------------

    console.log("Creating vector index on Function.src_embeddings");
    graph.query("CREATE VECTOR INDEX FOR (f:Function) ON (f.src_embeddings) OPTIONS {dimension:1536, similarityFunction:'euclidean'}");
}

function create_module(file: string, graph: Graph) {
    // Create module node
    const file_name = file.split("/")[-1];
    const params = {'name': file_name};
    
    const q = "MERGE (m:Module {name: $name}) RETURN ID(m)";
    graph.query(q, {params: params});

    // module imports
    // for imp in node.body:
    //     if isinstance(imp, ast.Import):
    //         for alias in imp.names:
    //             params = {'m_id': m_id, 'import_name': alias.name}
    //             q = """MATCH (m:Module)
    //                    WHERE ID(m) = $m_id
    //                    MERGE (i:Module {name: $import_name})
    //                    MERGE (m)-[:IMPORTS]->(i)"""
    //             graph.query(q, params)
}

function create_class(file: string, graph: Graph, class_name: string,
	src_start: int, src_end: int) {
    
    // create class node
    const file_name = file.split("/")[-1];

    const params = {'name': node.name,
              'file_name': file_name,
              'src_start': node.lineno,
              'src_end': node.end_lineno};

    // create Class and connect to Module
    const q = `MERGE (c:Class {name: $name, file_name: $file_name,
           src_start:$src_start, src_end: $src_end})
           WITH c
           MATCH (m:Module {name: $file_name})
           MERGE (m)-[:CONTAINS]->(c)`;
    graph.query(q, {params: params});
}

function create_function(file: string, graph: Graph, function_name: string,
	parent: string, args: string[], src_start: int, src_end: int) {
    // scan function arguments
    if(args[0] == "self") {
    	args = args[1:];
    }

    // create function node
    const file_name = file.split("/")[-1];
    
    // function source code
    let src_code: string;

    fs.readFile(file, 'utf8', function (err: any, source: string) {
		if (err) {
			return console.log(err);
		}
		src_code = source;
	});

    let params = {'name': function_name, 'file_name': file_name, 'src_code': src_code,
              'src_start': src_start, 'src_end': src_end, 'args': args};

    q = `CREATE (f:Function {name: $name, file_name: $file_name,
           src_code: $src_code, src_start: $src_start, src_end: $src_end,
           args: $args})
           RETURN ID(f)`;
    f_id = graph.query(q, {params: params}).result_set[0][0];

    
    // Connect function to parent
    params = {'f_id': f_id, 'c_name': parent};

    q = `MATCH (c:Class {name: $c_name})
    MATCH (f:Function) WHERE ID(f) = $f_id
    MERGE (c)-[:CONTAINS]->(f)`;
    graph.query(q, params);

    // if isinstance(parent, ast.Module):
    //     params = {'m_name': file_name, 'f_id': f_id}
    //     q = """MATCH (m:Module {name: $m_name})
    //            MATCH (f:Function) WHERE ID(f) = $f_id
    //            MERGE (m)-[:CONTAINS]->(f)"""
    //     graph.query(q, params)
    // elif isinstance(parent, ast.ClassDef):
    //     params = {'f_id': f_id, 'c_name': parent.name}
    //     q = """MATCH (c:Class {name: $c_name})
    //            MATCH (f:Function) WHERE ID(f) = $f_id
    //            MERGE (c)-[:CONTAINS]->(f)"""
    //     graph.query(q, params)
    // elif isinstance(parent, ast.FunctionDef):
    //     params = {'f_id': f_id,
    //               'parent_name': parent.name, 'parent_src_start': parent.lineno,
    //               'parent_src_end': parent.end_lineno, 'file_name': file_name}
    //     q = """MATCH (p:Function {name: $parent_name, src_start: $parent_src_start, src_end: $parent_src_end, file_name: $file_name})
    //            MATCH (f2:Function) WHERE ID(f2) = $f_id
    //            MERGE (p)-[:CONTAINS]->(f2)"""
    //     graph.query(q, params)
    // else:
    //     raise("Unhandled parent type")
}

function inherit_class(file: string, graph: Graph, node) {
    //-------------------------------------------------------------------------
    // determine class inheritance
    //-------------------------------------------------------------------------

    //inheritance = []
    //for base in node.bases:
    //    if isinstance(base, ast.Name):
    //        inheritance.append(base.id)

    //file_name = file.split("/")[-1]
    //params = {'name': node.name,
    //          'file_name': file_name,
    //          'src_start': node.lineno,
    //          'src_end': node.end_lineno,
    //          'inheritance': inheritance}

    //q = """MATCH (c:Class {name: $name, file_name: $file_name,
    //       src_start:$src_start, src_end: $src_end}), (base:Class)
    //       WHERE base.name IN $inheritance
    //       MERGE (c)-[:INHERITS]->(base)"""
    //
    //graph.query(q, params)
}

function create_function_call
(
	file: string,	       // file in which call occurred
	graph: Graph,          // graph object
	caller: string,        // who've invoked the call
	callee: string,        // who's being called
	caller_src_start: int, // caller definition start
	caller_src_end: int,   // caller definition end
	call_src_start: int,   // first line on which call occurred
	call_src_end: int      // last line on which call occurred
) {
    // make sure callee exists
    // determine callee type (either a function or a class)
    let params = {'name': callee};
    let q = `OPTIONAL MATCH (c:Class {name: $name})
           OPTIONAL MATCH (f:Function {name: $name})
           RETURN ID(c), ID(f) LIMIT 1`;

	let res  = graph.query(q, {params: params}).result_set;
    let c_id = res[0][0];
    let f_id = res[0][1];

    const callee_id = c_id !== null ? c_id : f_id;
    if (callee_id == null) {
        console.log("Callee not found");
        return;
    }

    const file_name = file.split("/")[-1];
    const params = {'file_name': file_name,
    				'callee_id': callee_id,
    				'caller_name': caller,
    				'caller_src_start': caller_src_start,
    				'caller_src_end': caller_src_end,
    				'call_src_start': call_src_end
    				'call_src_end': call_src_end};

    // connect caller to callee
    q = `MATCH (callee), (caller)
    		WHERE ID(callee) = $callee_id AND
				  caller.name = $caller_name AND
    		      caller.file_name = $file_name AND
    		      caller.src_start = $caller_src_start AND
    		      caller.src_end = $caller_src_end
			MERGE (caller)-[:CALLS {file_name: $file_name, src_start: $call_src_start, src_end:$call_src_end}]->(callee)`;

    graph.query(q, {params: params});
}

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

let param_query: Parser.Query;

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
	let class_node      = match.captures[0].node;
	let class_name      = match.captures[1].node.text;	
	let class_src_end   = class_node.endPosition.row;
	let class_src_start = class_node.startPosition.row;

	// Match all function definition within the current class
	let function_matches = function_definition_query.matches(class_node);
	for (let function_match of function_matches) {	
		processFunctionDeclaration(source_file, function_match);
	}
}

// Process function declaration
function processFunctionDeclaration(source_file: string, match: Parser.QueryMatch) {	
	let function_node   = match.captures[0].node;
	let function_name   = match.captures[1].node.text;
	let function_params = match.captures[2].node;

	//-------------------------------------------------------------------------
	// Extract function params
	//-------------------------------------------------------------------------

	let params: string[] = [];
	for (let i = 0; i < function_params.namedChildCount; i++) {
		let child_node = function_params.namedChild(i);
		// if parameter is an identifier e.g. f(a)
		// then simply 
		if(child_node.type == 'identifier') {
			params.push(child_node.text);
		} else {
			let identifier_matches = param_query.matches(child_node)[0].captures;
			const identifierNode = identifier_matches[0].node;
			params.push(identifierNode.text);
		}
	}

	let function_src_end   = function_node.endPosition.row;
	let function_src_start = function_node.startPosition.row;

	// Match all function calls within the current function
	let function_call_matches = function_call_query.matches(function_node);

	for (let function_call of function_call_matches) {
		let callee = function_call.captures[0].node.text;
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
	
	param_query               = Python.query(`((identifier) @identifier)`);
	function_call_query 	  = Python.query(`((call function: (identifier) @function-name))`);
	class_definition_query    = Python.query(`(class_definition name: (identifier) @class-name) @class-definition`);
	function_definition_query = Python.query(`((function_definition name: (identifier) @function-name parameters: (parameters) @parameters) @function-definition)`);

	// Download Github Repo into a temporary folder
	// Create temporary folder

	const tmp_dir = os.tmpdir();
	console.log("Temporary directory: " + tmp_dir);

	// const url = "https://github.com/falkorDB/falkordb-py";

	let body = await request.json();
	let url = body.url;
	url = "https://github.com/falkorDB/falkordb-py";
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