import { Graph } from 'falkordb';

//-----------------------------------------------------------------------------
// Graph operations
//-----------------------------------------------------------------------------

// Create graph indices
export async function create_indices
(
    graph: Graph
) {
    //-------------------------------------------------------------------------
    // index "name" attribute
    //-------------------------------------------------------------------------

    console.log("Creating range index on Class.name");
    await graph.query("CREATE INDEX FOR (c:Class) ON (c.name)");    

    console.log("Creating range index on Module.name");
    await graph.query("CREATE INDEX FOR (m:Module) ON (m.name)");

    console.log("Creating range index on Function.name");
    await graph.query("CREATE INDEX FOR (f:Function) ON (f.name)");

    //-------------------------------------------------------------------------
    // index "src_embeddings" attribute
    //-------------------------------------------------------------------------

    console.log("Creating vector index on Function.src_embeddings");
    await graph.query("CREATE VECTOR INDEX FOR (f:Function) ON (f.src_embeddings) OPTIONS {dimension:1536, similarityFunction:'euclidean'}");
}

// Create Module node
export async function create_module
(
	file: string,
	graph: Graph
) {
    // Create module node
    const file_components = file.split("/");
    const file_name = file_components[file_components.length - 1];
    const params = {'name': file_name};
    
    const q = "MERGE (m:Module {name: $name}) RETURN ID(m)";
    await graph.query(q, {params: params});
}

// Create Class node
export async function create_class
(
	file: string,
	graph: Graph,
	class_name: string,
	src_start: number,
	src_end: number
) {
    // create class node
    const file_components = file.split("/");
    const file_name = file_components[file_components.length - 1];

    const params = {'name': class_name,
              'file_name': file_name,
              'src_start': src_start,
              'src_end': src_end};

    // create Class and connect to Module
    const q = `MERGE (c:Class {name: $name, file_name: $file_name,
           src_start:$src_start, src_end: $src_end})
           WITH c
           MATCH (m:Module {name: $file_name})
           MERGE (m)-[:CONTAINS]->(c)`;
    await graph.query(q, {params: params});
}

export async function inherit_class
(
	file: string,
	graph: Graph,
	node: any
) {
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

// Create Function node
export async function create_function
(
	file: string,
	graph: Graph,
	function_name: string,
	parent: string,
	args: string[],
	src_start: number,
	src_end: number,
	src: string
) {
    //-------------------------------------------------------------------------
    // scan function arguments
    //-------------------------------------------------------------------------

    // discard 'self' argument
    if(args.length > 0 && args[0] == "self") {
    	args.shift();
    }

    // create function node
    const file_components = file.split("/");
    const file_name = file_components[file_components.length - 1];

    let params: any = {'name':       function_name,
                       'file_name':  file_name,
    			        'src_code':  src,
    			        'src_start': src_start,
    			        'src_end':   src_end,
    			        'args':      args};

    let q = `CREATE (f:Function {name: $name, file_name: $file_name,
           src_code: $src_code, src_start: $src_start, src_end: $src_end,
           args: $args})
           RETURN ID(f) as func_id`;

    let result: any = await graph.query(q, {params: params});
    let f_id = result.data[0]['func_id'];

    //-------------------------------------------------------------------------
    // Connect function to parent
    //-------------------------------------------------------------------------

    params = {'f_id': f_id, 'parent': parent};

    q = `MATCH (parent {name: $parent})
    MATCH (f:Function) WHERE ID(f) = $f_id
    MERGE (parent)-[:CONTAINS]->(f)`;
    await graph.query(q, {params: params});
}

// Create function call
export async function create_function_call
(
	file: string,	          // file in which call occurred
	graph: Graph,             // graph object
	caller: string,           // who've invoked the call
	callee: string,           // who's being called
	caller_src_start: number, // caller definition start
	caller_src_end: number,   // caller definition end
	call_src_start: number,   // first line on which call occurred
	call_src_end: number      // last line on which call occurred
) {
    // make sure callee exists
    // determine callee type (either a function or a class)
    let params: any = {'name': callee};
    let q = `OPTIONAL MATCH (c:Class {name: $name})
           OPTIONAL MATCH (f:Function {name: $name})
           RETURN ID(c) as c_id, ID(f) as f_id LIMIT 1`;

	let res: any = await graph.query(q, {params: params});
    let c_id = res.data[0]['c_id'];
    let f_id = res.data[0]['f_id'];

    const callee_id = c_id !== null ? c_id : f_id;
    if (callee_id == null) {
        //console.log("Callee: " + callee + " not found");
        return;
    }

    // create function node
    const file_components = file.split("/");
    const file_name = file_components[file_components.length - 1];

    params = {'file_name':         file_name,
			   'callee_id':        callee_id,
    		   'caller_name':      caller,
    		   'caller_src_start': caller_src_start,
    		   'caller_src_end':   caller_src_end,
    		   'call_src_start':   call_src_end,
    		   'call_src_end':     call_src_end};

    // connect caller to callee
	q = `MATCH (callee), (caller)
		 WHERE ID(callee) = $callee_id AND
			   caller.name = $caller_name AND
    		   caller.file_name = $file_name AND
    		   caller.src_start = $caller_src_start AND
    		   caller.src_end = $caller_src_end
		 MERGE (caller)-[:CALLS {file_name: $file_name, src_start: $call_src_start, src_end:$call_src_end}]->(callee)`;

    await graph.query(q, {params: params});
}

export async function projectGraph
(
	graph: Graph
) {
	let result = await graph.query(`MATCH (n) RETURN n`);
	let nodes = result.data;

	result = await graph.query(`MATCH ()-[e]->() RETURN e`);
	let edges = result.data;

	return [nodes, edges];
}