import io
import os
from ..utils import *
from pathlib import Path
from ...entities import *
from ...graph import Graph
from typing import Optional
from ..analyzer import AbstractAnalyzer

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node

C_LANGUAGE = Language(tsc.language())

import logging
logger = logging.getLogger('code_graph')

class CAnalyzer(AbstractAnalyzer):
    def __init__(self) -> None:
        self.parser = Parser(C_LANGUAGE)

    def process_pointer_declaration(self, node: Node) -> tuple[str, int]:
        """
        Processes a pointer declaration node to determine the argument name and pointer count.

        Args:
            node (Node): The AST node representing a pointer declaration.

        Returns:
            Tuple[str, int]: A tuple containing the argument name and the pointer count.
        """

        assert(node.type == 'pointer_declarator')

        text = node.text.decode('utf-8')
        idx = max(text.rfind(' '), text.rfind('*')) + 1
        name = text[idx:]
        t = text[:idx]

        return (t, name)

    def process_parameter_declaration(self, node: Node) -> tuple[bool, str, int, str]:
        """
        Processes a parameter declaration node to determine its properties.

        Args:
            node (Node): The AST node representing a parameter declaration.

        Returns:
            Tuple[bool, str, int, Optional[str]]: A tuple containing:
                - A boolean indicating if the parameter is const.
                - A string representing the argument type.
                - An integer representing the pointer count.
                - An optional string for the argument name (None if not found).
        """

        assert(node.type == 'parameter_declaration')

        const    = False
        pointer  = 0
        arg_name = ''
        arg_type = ''

        for child in node.children:
            t = child.type

            if t == 'type_qualifier':
                child = child.children[0]
                if child.type == 'const':
                    const = True

            elif t == 'type_identifier':
                arg_type = child.text.decode('utf-8')

            elif t == 'identifier':
                arg_name = child.text.decode('utf-8')

            elif t == 'primitive_type':
                arg_type = child.text.decode('utf-8')

            elif t == 'pointer_declarator':
                pointer_arg_name, arg_name = self.process_pointer_declaration(child)
                arg_type += pointer_arg_name

            elif t == 'sized_type_specifier':
                arg_type = child.text.decode('utf-8')

        return (const, arg_type, pointer, arg_name)

    def process_function_definition_node(self, node: Node, path: Path,
                                         source_code: str) -> Optional[Function]:
        """
        Processes a function definition node to extract function details.

        Args:
            node (Node): The AST node representing a function definition.
            path (Path): The file path where the function is defined.

        Returns:
            Optional[Function]: A Function object containing details about the function, or None if the function name cannot be determined.
        """

        # Extract function name
        res = find_child_of_type(node, 'function_declarator')
        if res is None:
            return None

        function_declarator = res[0]

        res = find_child_of_type(function_declarator, 'identifier')
        if res is None:
            return None

        identifier = res[0]
        function_name = identifier.text.decode('utf-8')
        logger.info(f"Function declaration: {function_name}")

        # Extract function return type
        res = find_child_of_type(node, 'primitive_type')
        ret_type = 'Unknown'
        if res is not None:
            ret_type = res[0]
            ret_type = ret_type.text.decode('utf-8')

        # Extract function parameters
        args = []
        res = find_child_of_type(function_declarator, 'parameter_list')
        if res is not None:
            parameters = res[0]

            # Extract arguments and their types
            for child in parameters.children:
                if child.type == 'parameter_declaration':
                    arg = self.process_parameter_declaration(child)
                    args.append(arg)

        # Extract function definition line numbers
        start_line = node.start_point[0]
        end_line = node.end_point[0]

        # Create Function object
        docs = ''
        src = source_code[node.start_byte:node.end_byte]
        f = Function(str(path), function_name, docs, ret_type, src, start_line, end_line)

        # Add arguments to Function object
        for arg in args:
            const   = arg[0]
            t       = arg[1]
            pointer = arg[2]
            name    = arg[3]

            # Skip f(void)
            if name is None and t == 'void':
                continue

            type_str = 'const ' if const else ''
            type_str += t
            type_str += '*' * pointer

            f.add_argument(name, type_str)

        return f

    def process_function_definition(self, parent: File, node: Node, path: Path,
                                    graph: Graph, source_code: str) -> None:
        """
        Processes a function definition node and adds it to the graph.

        Args:
            parent (File): The parent File object.
            node (Node): The AST node representing the function definition.
            path (Path): The file path where the function is defined.
            graph (Graph): The Graph object to which the function entity will be added.

        Returns:
            None
        """

        assert(node.type == 'function_definition')

        entity = self.process_function_definition_node(node, path, source_code)
        if entity is not None:
            # Add Function object to the graph
            try:
                graph.add_function(entity)
            except Exception:
                logger.error(f"Failed creating function: {entity}")
                entity = None

        if entity is not None:
            # Connect parent to entity
            graph.connect_entities('DEFINES', parent.id, entity.id)

    def process_field_declaration(self, node: Node) -> Optional[tuple[str, str]]:
        """
        Processes a field declaration node to extract field name and type.

        Args:
            node (Node): The AST node representing a field declaration.

        Returns:
            Optional[Tuple[str, str]]: A tuple containing the field name and type, or None if either could not be determined.
        """

        assert(node.type == 'field_declaration')

        const = False
        field_name = None
        field_type = ''

        for child in node.children:
            if child.type == 'field_identifier':
                field_name = child.text.decode('utf-8')
            elif child.type == 'type_qualifier':
                const = True
            elif child.type == 'struct_specifier':
                # TODO: handle nested structs
                # TODO: handle union
                pass
            elif child.type == 'primitive_type':
                field_type = child.text.decode('utf-8')
            elif child.type == 'sized_type_specifier':
                field_type = child.text.decode('utf-8')
            elif child.type == 'pointer_declarator':
                pointer_field_type, field_name = self.process_pointer_declaration(child)
                field_type += pointer_field_type
            elif child.type == 'array_declarator':
                field_type += '[]'
                field_name = child.children[0].text.decode('utf-8')
            else:
                continue

        if field_type is not None and const is True:
            field_type = f'const {field_type}'

        if field_name is not None and field_type is not None:
            return (field_name, field_type)
        else:
            return None

    def process_struct_specifier_node(self, node: Node, path: Path) -> Optional[Struct]:
        """
        Processes a struct specifier node to extract struct fields.

        Args:
            node (Node): The AST node representing the struct specifier.
            path (Path): The file path where the struct is defined.

        Returns:
            Optional[Struct]: A Struct object containing details about the struct, or None if the struct name or fields could not be determined.
        """

        # Do not process struct without a declaration_list
        res = find_child_of_type(node, 'field_declaration_list')
        if res is None:
            return None

        field_declaration_list = res[0]

        # Extract struct name
        res = find_child_of_type(node, 'type_identifier')
        if res is None:
            return None

        type_identifier = res[0]
        struct_name = type_identifier.text.decode('utf-8')

        start_line = node.start_point[0]
        end_line   = node.end_point[0]
        s = Struct(str(path), struct_name, '', start_line, end_line)

        # Collect struct fields
        for child in field_declaration_list.children:
            if child.type == 'field_declaration':
                res = self.process_field_declaration(child)
                if res is None:
                    return None
                else:
                    field_name, field_type = res
                    s.add_field(field_name, field_type)

        return s

    def process_struct_specifier(self, parent: File, node: Node, path: Path,
                                 graph: Graph) -> Node:
        """
        Processes a struct specifier node to extract struct details and adds it to the graph.

        Args:
            parent (File): The parent File object.
            node (Node): The AST node representing the struct specifier.
            path (Path): The file path where the struct is defined.
            graph (Graph): The Graph object to which the struct entity will be added.

        Returns:
            Optional[Node]: The processed AST node representing the struct specifier if successful, otherwise None.

        Raises:
            AssertionError: If the provided node is not of type 'struct_specifier'.
        """

        assert(node.type == 'struct_specifier')

        entity = self.process_struct_specifier_node(node, path)
        if entity is not None:
            # Add Struct object to the graph
            try:
                graph.add_struct(entity)
            except Exception:
                logger.warning(f"Failed creating struct: {entity}")
                entity = None

        if entity is not None:
            # Connect parent to entity
            graph.connect_entities('DEFINES', parent.id, entity.id)

    def process_include_directive(self, parent: File, node: Node, path: Path, graph: Graph) -> None:
        """
        Processes an include directive node to create an edge between files.

        Args:
            parent (File): The parent File object.
            node (Node): The AST node representing the include directive.
            path (Path): The file path where the include directive is found.
            graph (Graph): The Graph object to which the file entities and edges will be added.

        Returns:
            None
        """

        assert(node.type == 'system_lib_string' or node.type == 'string_literal')
        
        
        try:
            included_file_path = node.text.decode('utf-8').strip('"<>')
            if not included_file_path:
                logger.warning("Empty include path found in %s", path)
                return
            
            # Normalize and validate path
            normalized_path = os.path.normpath(included_file_path)
        except UnicodeDecodeError as e:
            logger.error("Failed to decode include path in %s: %s", path, e)
            return

        splitted = os.path.splitext(normalized_path)
        if len(splitted) < 2:
            logger.warning("Include path has no extension: %s", included_file_path)
            return

        # Create file entity for the included file
        path = os.path.dirname(normalized_path)
        name = os.path.basename(normalized_path)
        ext = splitted[1]
        included_file = File(path, name, ext)
        graph.add_file(included_file)

        # Connect the parent file to the included file
        graph.connect_entities('INCLUDES', parent.id, included_file.id)

    def first_pass(self, path: Path, f: io.TextIOWrapper, graph:Graph) -> None:
        """
        Perform the first pass processing of a C source file or header file.

        Args:
            path (Path): The path to the C source file or header file.
            f (io.TextIOWrapper): The file object representing the opened C source file or header file.
            graph (Graph): The Graph object where entities will be added.

        Returns:
            None

        Raises:
            None

        This function processes the specified C source file or header file to extract and add function definitions
        and struct definitions to the provided graph object.

        - If the file path does not end with '.c' or '.h', it logs a debug message and skips processing.
        - It creates a File entity representing the file and adds it to the graph.
        - It parses the file content using a parser instance (`self.parser`).
        - Function definitions and struct definitions are extracted using Tree-sitter queries.
        - Each function definition is processed using `self.process_function_definition`.
        - Each struct definition is processed using `self.process_struct_specifier`.
        """

        if path.suffix != '.c' and path.suffix != '.h':
            logger.debug(f"Skipping none C file {path}")
            return

        logger.info(f"Processing {path}")

        # Create file entity
        file = File(os.path.dirname(path), path.name, path.suffix)
        graph.add_file(file)

        # Parse file
        source_code = f.read()
        tree = self.parser.parse(source_code)
        try:
            source_code = source_code.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed decoding source code: {e}")
            source_code = ''

        # Process function definitions
        query = C_LANGUAGE.query("(function_definition) @function")
        captures = query.captures(tree.root_node)
        # captures: {'function':
        #   [<Node type=function_definition, start_point=(0, 0), end_point=(7, 1)>,
        #    <Node type=function_definition, start_point=(15, 0), end_point=(18, 1)>
        #   ]
        # }

        if 'function' in captures:
            functions = captures['function']
            for node in functions:
                self.process_function_definition(file, node, path, graph, source_code)

        # Process struct definitions
        query = C_LANGUAGE.query("(struct_specifier) @struct")
        captures = query.captures(tree.root_node)
        
        if 'struct' in captures:
            structs = captures['struct']
            # captures: {'struct':
            #   [
            #       <Node type=struct_specifier, start_point=(9, 0), end_point=(13, 1)>
            #   ]
            # }
            for node in structs:
                self.process_struct_specifier(file, node, path, graph)

        # Process include directives
        query = C_LANGUAGE.query("(preproc_include [(string_literal) (system_lib_string)] @include)")
        captures = query.captures(tree.root_node)

        if 'include' in captures:
            includes = captures['include']
            for node in includes:
                self.process_include_directive(file, node, path, graph)

    def second_pass(self, path: Path, f: io.TextIOWrapper, graph: Graph) -> None:
        """
        Perform the second pass processing of a C source file or header file to establish function call relationships.

        Args:
            path (Path): The path to the C source file or header file.
            f (io.TextIOWrapper): The file object representing the opened C source file or header file.
            graph (Graph): The Graph object containing entities (functions and files) to establish relationships.

        Returns:
            None

        This function processes the specified C source file or header file to establish relationships between
        functions based on function calls. It performs the following steps:

        - Checks if the file path ends with '.c' or '.h'. If not, logs a debug message and skips processing.
        - Retrieves the file entity (`file`) from the graph based on the file path.
        - Parses the content of the file using a parser instance (`self.parser`). If parsing fails, logs an error.
        - Uses Tree-sitter queries (`query_function_def` and `query_call_exp`) to locate function definitions and
          function invocations (calls) within the parsed AST (`tree.root_node`).
        - Iterates over captured function definitions (`function_defs`) and their corresponding function calls
          (`function_calls`). For each function call:
          - Retrieves or creates a function entity (`callee_f`) in the graph.
          - Connects the caller function (`caller_f`) to the callee function (`callee_f`) using a 'CALLS' edge in
            the graph.

        Note:
        - This function assumes that function calls to native functions (e.g., 'printf') will create missing
          function entities (`Function` objects) and add them to the graph.

        Example usage:
            ```
            second_pass(Path('/path/to/file.c'), open('/path/to/file.c', 'r'), graph)
            ```
        """

        if path.suffix != '.c' and path.suffix != '.h':
            logger.debug(f"Skipping none C file {path}")
            return

        logger.info(f"Processing {path}")

        # Get file entity
        file = graph.get_file(os.path.dirname(path), path.name, path.suffix)
        if file is None:
            logger.error(f"File entity not found for: {path}")
            return

        try:
            # Parse file
            content = f.read()
            tree = self.parser.parse(content)
        except Exception as e:
            logger.error(f"Failed to process file {path}: {e}")
            return

        # Locate function invocation
        query_call_exp = C_LANGUAGE.query("(call_expression function: (identifier) @callee)")

        # Locate function definitions
        query_function_def = C_LANGUAGE.query("""
            (
                function_definition
                    declarator: (function_declarator
                        declarator: (identifier) @function_name)
            )""")

        function_defs = query_function_def.captures(tree.root_node)
        for function_def in function_defs:
            caller = function_def[0]
            caller_name = caller.text.decode('utf-8')
            caller_f = graph.get_function_by_name(caller_name)
            assert(caller_f is not None)

            function_calls = query_call_exp.captures(caller.parent.parent)
            for function_call in function_calls:
                callee = function_call[0]
                callee_name = callee.text.decode('utf-8')
                callee_f = graph.get_function_by_name(callee_name)

                if callee_f is None:
                    # Create missing function
                    # Assuming this is a call to a native function e.g. 'printf'
                    callee_f = Function('/', callee_name, None, None, None, 0, 0)
                    graph.add_function(callee_f)

                # Connect the caller and callee in the graph
                graph.connect_entities('CALLS', caller_f.id, callee_f.id)
