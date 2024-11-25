export const searchData: { searchInput: string; completedSearchInput?: string; }[] = [
    { searchInput: "test"},
    { searchInput: "set"},
    { searchInput: "low", completedSearchInput: "lower" },
    { searchInput: "as", completedSearchInput:  "ask"},
];

const categorizeCharacters = (characters: string[], expectedRes: boolean): { character: string; expectedRes: boolean }[] => {
  return characters.map(character => ({ character, expectedRes }));
};

export const specialCharacters: { character: string; expectedRes: boolean }[] = [
  ...categorizeCharacters(['%', '*', '(', ')', '-', '[', ']', '{', '}', ';', ':', '"', '|', '~'], true),
  ...categorizeCharacters(['!', '@', '#', '$', '^', '&', '_', '=', '+', "'", ',', '.', '<', '>', '/', '?', '\\', '`'], false)
];
