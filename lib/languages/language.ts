import path from 'path';
import Parser from 'web-tree-sitter';

const PYTHON_LANG = await Parser.Language.load(path.join(process.cwd(), 'app/parsers/tree-sitter-python.wasm'));

//-----------------------------------------------------------------------------
// Tree-Sitter queries
//-----------------------------------------------------------------------------
export class Language {

    public language: Parser.Language;

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

    constructor(language: Parser.Language,
        class_definition_query: Parser.Query,
        function_definition_query: Parser.Query,
        function_call_query: Parser.Query,
        function_attr_call_query: Parser.Query,
        identifier_query: Parser.Query) {

        this.language = language;
        this.class_definition_query = class_definition_query;
        this.function_definition_query = function_definition_query;
        this.function_call_query = function_call_query;
        this.function_attr_call_query = function_attr_call_query;
        this.identifier_query = identifier_query;
    }

}
