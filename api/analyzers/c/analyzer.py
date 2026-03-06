# import os
# from pathlib import Path

# from multilspy import SyncLanguageServer
# from ...entities import *
# from ...graph import Graph
# from typing import Optional
# from ..analyzer import AbstractAnalyzer

# import tree_sitter_c as tsc
# from tree_sitter import Language, Node

# import logging
# logger = logging.getLogger('code_graph')

# class CAnalyzer(AbstractAnalyzer):
#     def __init__(self) -> None:
#         super().__init__(Language(tsc.language()))

#     def get_entity_label(self, node: Node) -> str:
#         if node.type == 'struct_specifier':
#             return "Struct"
#         elif node.type == 'function_definition':
#             return "Function"
#         raise ValueError(f"Unknown entity type: {node.type}")

#     def get_entity_name(self, node: Node) -> str:
#         if node.type in ['struct_specifier', 'function_definition']:
#             return node.child_by_field_name('name').text.decode('utf-8')
#         raise ValueError(f"Unknown entity type: {node.type}")
    
#     def get_entity_docstring(self, node: Node) -> Optional[str]:
#         if node.type in ['struct_specifier', 'function_definition']:
#             body = node.child_by_field_name('body')
#             if body.child_count > 0 and body.children[0].type == 'expression_statement':
#                 docstring_node = body.children[0].child(0)
#                 return docstring_node.text.decode('utf-8')
#             return None
#         raise ValueError(f"Unknown entity type: {node.type}")  

#     def get_entity_types(self) -> list[str]:
#         return ['struct_specifier', 'function_definition']

#     def process_pointer_declaration(self, node: Node) -> tuple[str, int]:
#         """
#         Processes a pointer declaration node to determine the argument name and pointer count.

#         Args:
#             node (Node): The AST node representing a pointer declaration.

#         Returns:
#             Tuple[str, int]: A tuple containing the argument name and the pointer count.
#         """

#         assert(node.type == 'pointer_declarator')

#         text = node.text.decode('utf-8')
#         idx = max(text.rfind(' '), text.rfind('*')) + 1
#         name = text[idx:]
#         t = text[:idx]

#         return (t, name)

#     def process_parameter_declaration(self, node: Node) -> tuple[bool, str, int, str]:
#         """
#         Processes a parameter declaration node to determine its properties.

#         Args:
#             node (Node): The AST node representing a parameter declaration.

#         Returns:
#             Tuple[bool, str, int, Optional[str]]: A tuple containing:
#                 - A boolean indicating if the parameter is const.
#                 - A string representing the argument type.
#                 - An integer representing the pointer count.
#                 - An optional string for the argument name (None if not found).
#         """

#         assert(node.type == 'parameter_declaration')

#         const    = False
#         pointer  = 0
#         arg_name = ''
#         arg_type = ''

#         for child in node.children:
#             t = child.type

#             if t == 'type_qualifier':
#                 child = child.children[0]
#                 if child.type == 'const':
#                     const = True

#             elif t == 'type_identifier':
#                 arg_type = child.text.decode('utf-8')

#             elif t == 'identifier':
#                 arg_name = child.text.decode('utf-8')

#             elif t == 'primitive_type':
#                 arg_type = child.text.decode('utf-8')

#             elif t == 'pointer_declarator':
#                 pointer_arg_name, arg_name = self.process_pointer_declaration(child)
#                 arg_type += pointer_arg_name

#             elif t == 'sized_type_specifier':
#                 arg_type = child.text.decode('utf-8')

#         return (const, arg_type, pointer, arg_name)

#     def process_function_definition_node(self, node: Node, path: Path,
#                                          source_code: str) -> Optional[Function]:
#         """
#         Processes a function definition node to extract function details.

#         Args:
#             node (Node): The AST node representing a function definition.
#             path (Path): The file path where the function is defined.

#         Returns:
#             Optional[Function]: A Function object containing details about the function, or None if the function name cannot be determined.
#         """

#         # Extract function name
#         res = find_child_of_type(node, 'function_declarator')
#         if res is None:
#             return None

#         function_declarator = res[0]

#         res = find_child_of_type(function_declarator, 'identifier')
#         if res is None:
#             return None

#         identifier = res[0]
#         function_name = identifier.text.decode('utf-8')
#         logger.info(f"Function declaration: {function_name}")

#         # Extract function return type
#         res = find_child_of_type(node, 'primitive_type')
#         ret_type = 'Unknown'
#         if res is not None:
#             ret_type = res[0]
#             ret_type = ret_type.text.decode('utf-8')

#         # Extract function parameters
#         args = []
#         res = find_child_of_type(function_declarator, 'parameter_list')
#         if res is not None:
#             parameters = res[0]

#             # Extract arguments and their types
#             for child in parameters.children:
#                 if child.type == 'parameter_declaration':
#                     arg = self.process_parameter_declaration(child)
#                     args.append(arg)

#         # Extract function definition line numbers
#         start_line = node.start_point[0]
#         end_line = node.end_point[0]

#         # Create Function object
#         docs = ''
#         src = source_code[node.start_byte:node.end_byte]
#         f = Function(str(path), function_name, docs, ret_type, src, start_line, end_line)

#         # Add arguments to Function object
#         for arg in args:
#             const   = arg[0]
#             t       = arg[1]
#             pointer = arg[2]
#             name    = arg[3]

#             # Skip f(void)
#             if name is None and t == 'void':
#                 continue

#             type_str = 'const ' if const else ''
#             type_str += t
#             type_str += '*' * pointer

#             f.add_argument(name, type_str)

#         return f

#     def process_function_definition(self, parent: File, node: Node, path: Path,
#                                     graph: Graph, source_code: str) -> None:
#         """
#         Processes a function definition node and adds it to the graph.

#         Args:
#             parent (File): The parent File object.
#             node (Node): The AST node representing the function definition.
#             path (Path): The file path where the function is defined.
#             graph (Graph): The Graph object to which the function entity will be added.

#         Returns:
#             None
#         """

#         assert(node.type == 'function_definition')

#         entity = self.process_function_definition_node(node, path, source_code)
#         if entity is not None:
#             # Add Function object to the graph
#             try:
#                 graph.add_function(entity)
#             except Exception:
#                 logger.error(f"Failed creating function: {entity}")
#                 entity = None

#         if entity is not None:
#             # Connect parent to entity
#             graph.connect_entities('DEFINES', parent.id, entity.id)

#     def process_field_declaration(self, node: Node) -> Optional[tuple[str, str]]:
#         """
#         Processes a field declaration node to extract field name and type.

#         Args:
#             node (Node): The AST node representing a field declaration.

#         Returns:
#             Optional[Tuple[str, str]]: A tuple containing the field name and type, or None if either could not be determined.
#         """

#         assert(node.type == 'field_declaration')

#         const = False
#         field_name = None
#         field_type = ''

#         for child in node.children:
#             if child.type == 'field_identifier':
#                 field_name = child.text.decode('utf-8')
#             elif child.type == 'type_qualifier':
#                 const = True
#             elif child.type == 'struct_specifier':
#                 # TODO: handle nested structs
#                 # TODO: handle union
#                 pass
#             elif child.type == 'primitive_type':
#                 field_type = child.text.decode('utf-8')
#             elif child.type == 'sized_type_specifier':
#                 field_type = child.text.decode('utf-8')
#             elif child.type == 'pointer_declarator':
#                 pointer_field_type, field_name = self.process_pointer_declaration(child)
#                 field_type += pointer_field_type
#             elif child.type == 'array_declarator':
#                 field_type += '[]'
#                 field_name = child.children[0].text.decode('utf-8')
#             else:
#                 continue

#         if field_type is not None and const is True:
#             field_type = f'const {field_type}'

#         if field_name is not None and field_type is not None:
#             return (field_name, field_type)
#         else:
#             return None

#     def process_struct_specifier_node(self, node: Node, path: Path) -> Optional[Struct]:
#         """
#         Processes a struct specifier node to extract struct fields.

#         Args:
#             node (Node): The AST node representing the struct specifier.
#             path (Path): The file path where the struct is defined.

#         Returns:
#             Optional[Struct]: A Struct object containing details about the struct, or None if the struct name or fields could not be determined.
#         """

#         # Do not process struct without a declaration_list
#         res = find_child_of_type(node, 'field_declaration_list')
#         if res is None:
#             return None

#         field_declaration_list = res[0]

#         # Extract struct name
#         res = find_child_of_type(node, 'type_identifier')
#         if res is None:
#             return None

#         type_identifier = res[0]
#         struct_name = type_identifier.text.decode('utf-8')

#         start_line = node.start_point[0]
#         end_line   = node.end_point[0]
#         s = Struct(str(path), struct_name, '', start_line, end_line)

#         # Collect struct fields
#         for child in field_declaration_list.children:
#             if child.type == 'field_declaration':
#                 res = self.process_field_declaration(child)
#                 if res is None:
#                     return None
#                 else:
#                     field_name, field_type = res
#                     s.add_field(field_name, field_type)

#         return s

#     def process_struct_specifier(self, parent: File, node: Node, path: Path,
#                                  graph: Graph) -> Node:
#         """
#         Processes a struct specifier node to extract struct details and adds it to the graph.

#         Args:
#             parent (File): The parent File object.
#             node (Node): The AST node representing the struct specifier.
#             path (Path): The file path where the struct is defined.
#             graph (Graph): The Graph object to which the struct entity will be added.

#         Returns:
#             Optional[Node]: The processed AST node representing the struct specifier if successful, otherwise None.

#         Raises:
#             AssertionError: If the provided node is not of type 'struct_specifier'.
#         """

#         assert(node.type == 'struct_specifier')

#         entity = self.process_struct_specifier_node(node, path)
#         if entity is not None:
#             # Add Struct object to the graph
#             try:
#                 graph.add_struct(entity)
#             except Exception:
#                 logger.warning(f"Failed creating struct: {entity}")
#                 entity = None

#         if entity is not None:
#             # Connect parent to entity
#             graph.connect_entities('DEFINES', parent.id, entity.id)

#     def add_symbols(self, entity: Entity) -> None:
#         if entity.node.type == 'struct_specifier':
#             superclasses = entity.node.child_by_field_name("superclasses")
#             if superclasses:
#                 base_classes_query = self.language.query("(argument_list (_) @base_class)")
#                 base_classes_captures = base_classes_query.captures(superclasses)
#                 if 'base_class' in base_classes_captures:
#                     for base_class in base_classes_captures['base_class']:
#                         entity.add_symbol("base_class", base_class)
#         elif entity.node.type == 'function_definition':
#             query = self.language.query("(call) @reference.call")
#             captures = query.captures(entity.node)
#             if 'reference.call' in captures:
#                 for caller in captures['reference.call']:
#                     entity.add_symbol("call", caller)
#             query = self.language.query("(typed_parameter type: (_) @parameter)")
#             captures = query.captures(entity.node)
#             if 'parameter' in captures:
#                 for parameter in captures['parameter']:
#                     entity.add_symbol("parameters", parameter)
#             return_type = entity.node.child_by_field_name('return_type')
#             if return_type:
#                 entity.add_symbol("return_type", return_type)

#     def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, path: Path, node: Node) -> list[Entity]:
#         res = []
#         for file, resolved_node in self.resolve(files, lsp, path, node):
#             type_dec = self.find_parent(resolved_node, ['struct_specifier'])
#             res.append(file.entities[type_dec])
#         return res

#     def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, path: Path, node: Node) -> list[Entity]:
#         res = []
#         for file, resolved_node in self.resolve(files, lsp, path, node):
#             method_dec = self.find_parent(resolved_node, ['function_definition'])
#             if not method_dec:
#                 continue
#             if method_dec in file.entities:
#                 res.append(file.entities[method_dec])
#         return res
    
#     def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, path: Path, key: str, symbol: Node) -> Entity:
#         if key in ["parameters", "return_type"]:
#             return self.resolve_type(files, lsp, path, symbol)
#         elif key in ["call"]:
#             return self.resolve_method(files, lsp, path, symbol)
#         else:
#             raise ValueError(f"Unknown key {key}")

#     def second_pass(self, path: Path, graph: Graph) -> None:
#         """
#         Perform the second pass processing of a C source file or header file to establish function call relationships.

#         Args:
#             path (Path): The path to the C source file or header file.
#             f (io.TextIOWrapper): The file object representing the opened C source file or header file.
#             graph (Graph): The Graph object containing entities (functions and files) to establish relationships.

#         Returns:
#             None

#         This function processes the specified C source file or header file to establish relationships between
#         functions based on function calls. It performs the following steps:

#         - Checks if the file path ends with '.c' or '.h'. If not, logs a debug message and skips processing.
#         - Retrieves the file entity (`file`) from the graph based on the file path.
#         - Parses the content of the file using a parser instance (`self.parser`). If parsing fails, logs an error.
#         - Uses Tree-sitter queries (`query_function_def` and `query_call_exp`) to locate function definitions and
#           function invocations (calls) within the parsed AST (`tree.root_node`).
#         - Iterates over captured function definitions (`function_defs`) and their corresponding function calls
#           (`function_calls`). For each function call:
#           - Retrieves or creates a function entity (`callee_f`) in the graph.
#           - Connects the caller function (`caller_f`) to the callee function (`callee_f`) using a 'CALLS' edge in
#             the graph.

#         Note:
#         - This function assumes that function calls to native functions (e.g., 'printf') will create missing
#           function entities (`Function` objects) and add them to the graph.

#         Example usage:
#             ```
#             second_pass(Path('/path/to/file.c'), open('/path/to/file.c', 'r'), graph)
#             ```
#         """

#         if path.suffix != '.c' and path.suffix != '.h':
#             logger.debug(f"Skipping none C file {path}")
#             return

#         logger.info(f"Processing {path}")

#         # Get file entity
#         file = graph.get_file(os.path.dirname(path), path.name, path.suffix)
#         if file is None:
#             logger.error(f"File entity not found for: {path}")
#             return

#         try:
#             # Parse file
#             content = path.read_bytes()
#             tree = self.parser.parse(content)
#         except Exception as e:
#             logger.error(f"Failed to process file {path}: {e}")
#             return

#         # Locate function invocation
#         query_call_exp = self.language.query("(call_expression function: (identifier) @callee)")

#         # Locate function definitions
#         query_function_def = self.language.query("""
#             (
#                 function_definition
#                     declarator: (function_declarator
#                         declarator: (identifier) @function_name)
#             )""")

#         function_defs = query_function_def.captures(tree.root_node)
#         for function_def in function_defs:
#             caller = function_def[0]
#             caller_name = caller.text.decode('utf-8')
#             caller_f = graph.get_function_by_name(caller_name)
#             assert(caller_f is not None)

#             function_calls = query_call_exp.captures(caller.parent.parent)
#             for function_call in function_calls:
#                 callee = function_call[0]
#                 callee_name = callee.text.decode('utf-8')
#                 callee_f = graph.get_function_by_name(callee_name)

#                 if callee_f is None:
#                     # Create missing function
#                     # Assuming this is a call to a native function e.g. 'printf'
#                     callee_f = Function('/', callee_name, None, None, None, 0, 0)
#                     graph.add_function(callee_f)

#                 # Connect the caller and callee in the graph
#                 graph.connect_entities('CALLS', caller_f.id, callee_f.id)
