import twcolors from 'tailwindcss/colors'

export interface Category {
  name: string,
  index: number,
  show: boolean,
}

export interface Node {
  id: string,
  name: string,
  category: string,
  color: string,
}

export interface Edge {
  source: number,
  target: number,
  label: string,
}

const COLORS_ORDER = [
  "rose",
  "yellow",
  "teal",
  "fuchsia",
  "blue",
  "violet",
  "slate",
  "cyan",
  "orange",
  "red",
  "green",
  "pink",
]

export function getCategoryColorName(index: number): string {
  index = index<COLORS_ORDER.length ? index : 0
  return COLORS_ORDER[index]
}

function getCategoryColorValue(index: number): string {
  index = index<COLORS_ORDER.length ? index : 0
  let colorName = COLORS_ORDER[index]

  let colors = twcolors as any
  let color = colors[colorName]
  return color["500"]
}

export class Graph {

  private id: string;
  private categories: Category[];
  private elements: any[];

  private categoriesMap: Map<String, Category>;
  private nodesMap: Map<number, Node>;
  private edgesMap: Map<number, Edge>;

  private constructor(id: string, categories: Category[], elements: any[],
    categoriesMap: Map<String, Category>, nodesMap: Map<number, Node>, edgesMap: Map<number, Edge>) {
    this.id = id;
    this.categories = categories;
    this.elements = elements;
    this.categoriesMap = categoriesMap;
    this.nodesMap = nodesMap;
    this.edgesMap = edgesMap;
  }

  get Id(): string {
    return this.id;
  }

  get Categories(): Category[] {
    return this.categories;
  }

  get Elements(): any[] {
    return this.elements;
  }

  public static empty(): Graph {
    return new Graph("", [], [], new Map<String, Category>(), new Map<number, Node>(), new Map<number, Edge>())
  }

  public static create(results: any): Graph {
    let graph = Graph.empty()
    graph.extend(results)
    graph.id = results.id
    return graph
  }

  public extend(results: any): any[] {
    let newElements: any[] = []
    results.nodes.forEach((nodeData: any) => {
      let label = nodeData.label;
      // check if category already exists in categories
      let category = this.categoriesMap.get(label)
      if (!category) {
        category = { name: label, index: this.categoriesMap.size, show: true }
        this.categoriesMap.set(label, category)
        this.categories.push(category)
      }

      // check if node already exists in nodes
      let node = this.nodesMap.get(nodeData.id)
      if (node) {
        return
      }

      node = {
        id: nodeData.id.toString(),
        name: nodeData.name,
        color: getCategoryColorValue(category.index),
        category: category.name,
      }
      this.nodesMap.set(nodeData.id, node)
      this.elements.push({ data: node })
      newElements.push({ data: node })
    })

    results.edges.forEach((edgeData: any) => {
      let edge = this.edgesMap.get(edgeData.id)
      if (edge) {
        return
      }

      let sourceId = edgeData.src.toString();
      let destinationId = edgeData.dest.toString()

      edge = {
        source: sourceId,
        target: destinationId,
        label: edgeData.type,
      }
      this.edgesMap.set(edgeData.id, edge)
      this.elements.push({ data: edge })
      newElements.push({ data: edge })
    })

    return newElements
  }
}