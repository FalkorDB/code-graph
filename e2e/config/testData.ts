export const searchData: { searchInput: string; completedSearchInput?: string; }[] = [
    { searchInput: "test"},
    { searchInput: "set"},
    { searchInput: "low", completedSearchInput: "lower_items" },
    { searchInput: "as", completedSearchInput:  "ask"},
];

const categorizeCharacters = (characters: string[], expectedRes: boolean): { character: string; expectedRes: boolean }[] => {
  return characters.map(character => ({ character, expectedRes }));
};

export const specialCharacters: { character: string; expectedRes: boolean }[] = [
  ...categorizeCharacters(['%', '*', '(', ')', '-', '[', ']', '{', '}', ';', ':', '"', '|', '~'], false),
  ...categorizeCharacters(['!', '@', '$', '^', '_', '=', '+', "'", ',', '.', '<', '>', '/', '?', '\\', '`', '&', '#'], true)
];

export const nodesPath: { firstNode: string; secondNode: string }[] = [
  { firstNode: "import_data", secondNode: "add_edge" },
  { firstNode: "test_kg_delete", secondNode: "list_graphs" },
];

export const nodes: { nodeName: string; }[] = [
  // { nodeName: "ask"},
  { nodeName: "add_edge" },
  { nodeName: "test_kg_delete"},
  { nodeName: "list_graphs"}
];

export const categories: string[] = ['File', 'Class', 'Function'];

export const graphs: { graphName: string; }[] = [
  { graphName: "GraphRAG-SDK" },
  { graphName: "click" },
];