import { Path } from '../page'

export interface GraphData {
  nodes: Node[],
  links: Link[],
}
export interface Category {
  name: string,
  index: number,
  show: boolean,
}

export type Node = {
  id: number,
  name: string,
  category: string,
  color: string,
  collapsed: boolean,
  expand: boolean,
  visibility: boolean,
  isPathSelected: boolean,
  isPath: boolean,
  [key: string]: any,
}

export type Link = {
  id: number,
  source: Node,
  target: Node,
  label: string,
  visibility: boolean,
  expand: boolean,
  collapsed: boolean,
  isPathSelected: boolean,
  isPath: boolean,

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
  private elements: GraphData;

  private categoriesMap: Map<string, Category>;
  private nodesMap: Map<number, Node>;
  private linksMap: Map<number, Link>;

  private constructor(id: string, categories: Category[], elements: GraphData,
    categoriesMap: Map<string, Category>, nodesMap: Map<number, Node>, edgesMap: Map<number, Link>) {
    this.id = id;
    this.categories = categories;
    this.elements = elements;
    this.categoriesMap = categoriesMap;
    this.nodesMap = nodesMap;
    this.linksMap = edgesMap;
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

  get Elements(): GraphData {
    return this.elements;
  }

  set Elements(elements: GraphData) {
    this.elements = elements;
  }

  get EdgesMap(): Map<number, Link> {
    return this.linksMap;
  }

  get NodesMap(): Map<number, Node> {
    return this.nodesMap;
  }

  public getElements(): (Node | Link)[] {
    return [...this.elements.nodes, ...this.elements.links]
  }

  public static empty(): Graph {
    return new Graph("", [], { nodes: [], links: [] }, new Map<string, Category>(), new Map<number, Node>(), new Map<number, Link>())
  }

  public static create(results: any, graphName: string): Graph {
    let graph = Graph.empty()
    graph.extend(results)
    graph.id = graphName
    return graph
  }

  public extend(results: any, collapsed = false, path?: Path): GraphData {
    let newElements: GraphData = { nodes: [], links: [] }

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
        if (path?.start?.id === nodeData.id || path?.end?.id === nodeData.id) {
          node.isPathSelected = true
        }
        return
      }

      node = {
        id: nodeData.id,
        name: nodeData.name,
        color: getCategoryColorValue(category.index),
        category: category.name,
        expand: false,
        visibility: true,
        collapsed,
        isPath: !!path,
        isPathSelected: path?.start?.id === nodeData.id || path?.end?.id === nodeData.id
      }
      Object.entries(nodeData.properties).forEach(([key, value]) => {
        node[key] = value
      })
      this.nodesMap.set(nodeData.id, node)
      this.elements.nodes.push(node)
      newElements.nodes.push(node)
    })

    if (!("edges" in results)) {
      results.edges = results.links 
    }

    results.edges.forEach((edgeData: any) => {
      let link = this.linksMap.get(edgeData.id)
      if (link) {
        link.isPath = !!path
        return
      }

      let sourceId = edgeData.src_node;
      let destinationId = edgeData.dest_node

      link = {
        id: edgeData.id,
        source: sourceId,
        target: destinationId,
        label: edgeData.relation,
        visibility: true,
        expand: false,
        collapsed,
        isPathSelected: false,
        isPath: !!path,
      }
      this.linksMap.set(edgeData.id, link)
      this.elements.links.push(link)
      newElements.links.push(link)
    })

    return newElements
  }

  public removeLinks() {
    this.elements = {
      nodes: this.elements.nodes,
      links: this.elements.links.map(link => {
        if (this.elements.nodes.map(n => n.id).includes(link.source.id) && this.elements.nodes.map(n => n.id).includes(link.target.id)) {
          return link
        }
        this.linksMap.delete(link.id)
      }).filter(link => link !== undefined)
    }
  }

  public visibleLinks(ids?: number[], visibility?: boolean) {
    this.elements.links.forEach(link => {
      if (ids && visibility !== undefined) {
        if (ids.includes(link.source.id) || ids.includes(link.target.id)) {
          link.visibility = visibility
        }
      } else {
        if (this.categories.find(category => category.name === link.source.category)?.show && this.categories.find(category => category.name === link.target.category)?.show) {
          link.visibility = true
        } else {
          link.visibility = false
        }
      }
    })
  }
}