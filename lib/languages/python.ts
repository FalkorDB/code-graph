import path from 'path';
import Parser from 'web-tree-sitter';
import Language from './language';

const PYTHON_LANG = await Parser.Language.load(path.join(process.cwd(), 'app/parsers/tree-sitter-python.wasm'));

//-----------------------------------------------------------------------------
// Tree-Sitter queries
//-----------------------------------------------------------------------------
export default class Python extends Language {

    constructor() {
        super(
            PYTHON_LANG,
            PYTHON_LANG.query(`(class_definition name: (identifier) @class-name) @class-definition`),
            PYTHON_LANG.query(`((function_definition name: (identifier) @function-name parameters: (parameters) @parameters) @function-definition)`),
            PYTHON_LANG.query(`((call function: (identifier) @function-name) @function-call)`),
            PYTHON_LANG.query(`((call function: (attribute object: (identifier) attribute: (identifier) @function-name )) @function-call)`),
            PYTHON_LANG.query(`((identifier) @identifier)`))
    }
}
