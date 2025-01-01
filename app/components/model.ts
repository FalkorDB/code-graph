import { LinkObject, NodeObject } from 'react-force-graph-2d'
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

export type Node = NodeObject<{
  id: number,
  name: string,
  category: string,
  color: string,
  collapsed: boolean,
  expand: boolean,
  visible: boolean,
  isPathSelected: boolean,
  isPath: boolean,
  [key: string]: any,
}>

export type Link = LinkObject<Node, {
  id: number,
  source: Node,
  target: Node,
  label: string,
  visible: boolean,
  expand: boolean,
  collapsed: boolean,
  isPathSelected: boolean,
  isPath: boolean,
  curve: number,
  [key: string]: any,
}>

const COLORS_ORDER_NAME = [
  "blue",
  "pink",
  "orange",
  "turquoise",
]

const COLORS_ORDER = [
  "#7466FF",
  "#FF66B3",
  "#FF804D",
  "#80E6E6",
]

export function getCategoryColorValue(index: number = 0): string {
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
        visible: true,
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

      let source = this.nodesMap.get(edgeData.src_node)
      let target = this.nodesMap.get(edgeData.dest_node)

      if (!source) {
        source = {
          id: edgeData.src_node,
          name: edgeData.src_node,
          color: getCategoryColorValue(),
          category: "",
          expand: false,
          visible: true,
          collapsed,
          isPath: !!path,
          isPathSelected: path?.start?.id === edgeData.src_node || path?.end?.id === edgeData.src_node
        }
      }

      if (!target) {
        target = {
          id: edgeData.dest_node,
          name: edgeData.dest_node,
          color: getCategoryColorValue(),
          category: "",
          expand: false,
          visible: true,
          collapsed,
          isPath: !!path,
          isPathSelected: path?.start?.id === edgeData.dest_node || path?.end?.id === edgeData.dest_node
        }
      }

      link = {
        id: edgeData.id,
        source,
        target,
        label: edgeData.relation,
        visible: true,
        expand: false,
        collapsed,
        isPathSelected: false,
        isPath: !!path,
        curve: 0
      }
      this.linksMap.set(edgeData.id, link)
      this.elements.links.push(link)
      newElements.links.push(link)
    })

    newElements.links.forEach(link => {
      const start = link.source
      const end = link.target
      const sameNodesLinks = this.Elements.links.filter(l => (l.source.id === start.id && l.target.id === end.id) || (l.target.id === start.id && l.source.id === end.id))
      const index = sameNodesLinks.findIndex(l => l.id === link.id) || 0
      const even = index % 2 === 0
      let curve

      if (start.id === end.id) {
        if (even) {
          curve = Math.floor(-(index / 2)) - 3
        } else {
          curve = Math.floor((index + 1) / 2) + 2
        }
      } else {
        console.log(link.curve)
        if (even) {
          curve = Math.floor(-(index / 2))
        } else {
          curve = Math.floor((index + 1) / 2)
        }

      }

      link.curve = curve * 0.1
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

  public visibleLinks(visible: boolean, ids?: number[]) {
    const elements = ids ? this.elements.links.filter(link => ids.includes(link.source.id) || ids.includes(link.target.id)) : this.elements.links

    elements.forEach(link => {
      if (visible && this.elements.nodes.map(n => n.id).includes(link.source.id) && link.source.visible && this.elements.nodes.map(n => n.id).includes(link.target.id) && link.target.visible) {
        // eslint-disable-next-line no-param-reassign
        link.visible = true
      }

      if (!visible && ((this.elements.nodes.map(n => n.id).includes(link.source.id) && !link.source.visible) || (this.elements.nodes.map(n => n.id).includes(link.target.id) && !link.target.visible))) {
        // eslint-disable-next-line no-param-reassign
        link.visible = false
      }
    })
  }
}