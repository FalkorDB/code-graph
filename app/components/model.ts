import twcolors from 'tailwindcss/colors'
import { Path } from '../page'

export interface Element {
  data: Node | Edge,
}

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
  [key: string]: any,
}

export interface Edge {
  source: number,
  target: number,
  label: string,
  [key: string]: any,
}

const COLORS_ORDER_NAME = [
  "pink",
  "yellow",
  "blue",
]

const COLORS_ORDER = [
  "#F43F5F",
  "#E9B306",
  "#15B8A6",
]

export function getCategoryColorValue(index: number): string {
  return COLORS_ORDER[index % COLORS_ORDER.length]
}

export function getCategoryColorName(index: number): string {
  return COLORS_ORDER_NAME[index % COLORS_ORDER.length]
}

export class Graph {

  private id: string;
  private categories: Category[];
  private elements: any[];

  private categoriesMap: Map<string, Category>;
  private nodesMap: Map<number, Node>;
  private edgesMap: Map<number, Edge>;

  private constructor(id: string, categories: Category[], elements: any[],
    categoriesMap: Map<string, Category>, nodesMap: Map<number, Node>, edgesMap: Map<number, Edge>) {
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

  get CategoriesMap(): Map<string, Category> {
    return this.categoriesMap;
  }

  get Elements(): Element[] {
    return this.elements;
  }

  get EdgesMap(): Map<number, Edge> {
    return this.edgesMap;
  }

  get NodesMap(): Map<number, Node> {
    return this.nodesMap;
  }

  public static empty(): Graph {
    return new Graph("", [], [], new Map<string, Category>(), new Map<number, Node>(), new Map<number, Edge>())
  }

  public static create(results: any, graphName: string): Graph {
    let graph = Graph.empty()
    graph.extend(results)
    graph.id = graphName
    return graph
  }

  public extend(results: any, collapsed = false, path?: Path): any[] {
    let newElements: any[] = []

    results.nodes.forEach((nodeData: any) => {
      let label = nodeData.labels[0];
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
        node.isPath = !!path
        if (path?.start?.id == nodeData.id || path?.end?.id == nodeData.id) {
          node.isPathStartEnd = true
        }
        node.isPath = !!path
        return
      }

      node = {
        id: nodeData.id.toString(),
        name: nodeData.name,
        color: getCategoryColorValue(category.index),
        category: category.name,
        expand: false,
        collapsed,
        isPath: !!path,
      }
      if (path?.start?.id == nodeData.id || path?.end?.id == nodeData.id) {
        node.isPathStartEnd = true
      }
      Object.entries(nodeData.properties).forEach(([key, value]) => {
        node[key] = value
      })
      this.nodesMap.set(nodeData.id, node)
      this.elements.push({ data: node })
      newElements.push({ data: node })
    })

    results.edges.forEach((edgeData: any) => {
      let edge = this.edgesMap.get(edgeData.id)
      if (edge) {
        edge.isPath = !!path
        return
      }

      let sourceId = edgeData.src_node.toString();
      let destinationId = edgeData.dest_node.toString()

      edge = {
        id: `_${edgeData.id}`,
        source: sourceId,
        target: destinationId,
        label: edgeData.relation,
        expand: false,
        collapsed,
        isPath: !!path,
      }
      this.edgesMap.set(edgeData.id, edge)
      this.elements.push({ data: edge })
      newElements.push({ data: edge })
    })

    return newElements
  }
}