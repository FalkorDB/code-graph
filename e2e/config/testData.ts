export const searchData: { searchInput: string; completedSearchInput?: string; }[] = [
    { searchInput: "test"},
    { searchInput: "set"},
    { searchInput: "lo", completedSearchInput: "load" },
    { searchInput: "as", completedSearchInput:  "ask"},
];

const categorizeCharacters = (characters: string[], expectedRes: boolean): { character: string; expectedRes: boolean }[] => {
  return characters.map(character => ({ character, expectedRes }));
};

export const specialCharacters: { character: string; expectedRes: boolean }[] = [
  ...categorizeCharacters(['%', '*', '(', ')', '-', '[', ']', '{', '}', ';', ':', '"', '|', '~'], false),
  ...categorizeCharacters(['!', '@', '$', '^', '=', '+', "'", ',', '<', '>', '/', '?', '\\', '`', '&', '#'], false),
  ...categorizeCharacters(['_', '.'], true)
];

export const nodesPath: { firstNode: string; secondNode: string }[] = [
  { firstNode: "merge_with", secondNode: "combine" },
  { firstNode: "import_data", secondNode: "add_node" }
];

export const nodes: { nodeName: string; }[] = [
  { nodeName: "add_edge" },
  { nodeName: "combine"},
  { nodeName: "ask"}
];

export const categories: string[] = ['File', 'Class', 'Function'];

export const graphs: { graphName: string; }[] = [
  { graphName: "GraphRAG-SDK" },
  { graphName: "flask" },
];