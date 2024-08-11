import path from 'path';
import Parser from 'web-tree-sitter';
import { Language } from 'web-tree-sitter';

const PYTHON_LANG = await Parser.Language.load(path.join(process.cwd(), 'app/parsers/tree-sitter-python.wasm'));

//-----------------------------------------------------------------------------
// Tree-Sitter queries
//-----------------------------------------------------------------------------
export class Python {

    public language: Language;

    // class definition tree-sitter query
    // responsible for matching class definition, in addition to extracting the class name
    public class_definition_query: Parser.Query;

    // function definition tree-sitter query
    // responsible for matching function definition, in addition to extracting the function name
    public function_definition_query: Parser.Query;

    // function call tree-sitter query
    // responsible for matching function calls, in addition to extracting the callee function name
    public function_call_query: Parser.Query;

    // function call tree-sitter query
    // responsible for matching function calls of type self.f()
    // in addition to extracting the callee function name
    public function_attr_call_query: Parser.Query;

    // identifier tree-sitter query
    // responsible for matching Identifier nodes
    public identifier_query: Parser.Query;

    constructor() {
        this.language = PYTHON_LANG;
        this.class_definition_query = PYTHON_LANG.query(`(class_definition name: (identifier) @class-name) @class-definition`);
        this.function_definition_query = PYTHON_LANG.query(`((function_definition name: (identifier) @function-name parameters: (parameters) @parameters) @function-definition)`);
        this.function_call_query = PYTHON_LANG.query(`((call function: (identifier) @function-name) @function-call)`);
        this.function_attr_call_query = PYTHON_LANG.query(`((call function: (attribute object: (identifier) attribute: (identifier) @function-name )) @function-call)`);
        this.identifier_query = PYTHON_LANG.query(`((identifier) @identifier)`);

    }

}
