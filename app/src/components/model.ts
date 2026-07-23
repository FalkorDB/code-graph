import { Path } from '@/lib/utils'

export interface GraphData {
  nodes: Node[],
  links: Link[],
}
export interface Category {
  name: string,
  index: number,
  show: boolean,
}

export interface Label {
  name: string,
}

export interface Node {
  id: number,
  category: string,
  color: string,
  visible: boolean,
  collapsed: boolean,
  expand: boolean,
  isPathSelected: boolean,
  isPath: boolean,
  data: {
    name: string,
    [key: string]: any,
  }
}
export interface Link {
  id: number,
  source: number,
  target: number,
  label: string,
  visible: boolean,
  collapsed: boolean,
  isPathSelected: boolean,
  isPath: boolean,
  color: string,
  data: {
    [key: string]: any,
  },
}

const COLORS_ORDER_NAME = [
  "graph-purple",
  "graph-pink",
  "graph-orange",
  "graph-turquoise",
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
  private labels: Label[];
  private elements: GraphData;
  private categoriesMap: Map<string, Category>;
  private labelsMap: Map<string, Label>;
  private nodesMap: Map<number, Node>;
  private linksMap: Map<number, Link>;

  private constructor(id: string, categories: Category[], labels: Label[], elements: GraphData,
    categoriesMap: Map<string, Category>, labelsMap: Map<string, Label>, nodesMap: Map<number, Node>, edgesMap: Map<number, Link>) {
    this.id = id;
    this.categories = categories;
    this.labels = labels;
    this.elements = elements;
    this.categoriesMap = categoriesMap;
    this.labelsMap = labelsMap;
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

  get Labels(): Label[] {
    return this.labels;
  }

  get LabelsMap(): Map<string, Label> {
    return this.labelsMap;
  }

  get Elements(): GraphData {
    return this.elements;
  }

  set Elements(elements: GraphData) {
    this.elements = elements;
  }

  get LinksMap(): Map<number, Link> {
    return this.linksMap;
  }

  get NodesMap(): Map<number, Node> {
    return this.nodesMap;
  }

  public getElements(): (Node | Link)[] {
    return [...this.elements.nodes, ...this.elements.links]
  }

  public static empty(): Graph {
    return new Graph("", [], [], { nodes: [], links: [] }, new Map<string, Category>(), new Map<string, Label>(), new Map<number, Node>(), new Map<number, Link>())
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
        color: getCategoryColorValue(category.index),
        category: category.name,
        expand: false,
        visible: true,
        collapsed,
        isPath: !!path,
        isPathSelected: path?.start?.id === nodeData.id || path?.end?.id === nodeData.id,
        data: {
          ...nodeData.properties,
        }
      }

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
          color: getCategoryColorValue(),
          category: "",
          expand: false,
          visible: true,
          collapsed,
          isPath: !!path,
          isPathSelected: path?.start?.id === edgeData.src_node || path?.end?.id === edgeData.src_node,
          data: {
            name: edgeData.src_node
          }

        }
        this.nodesMap.set(edgeData.src_node, source)
        this.elements.nodes.push(source)
        newElements.nodes.push(source)
      }

      if (!target) {
        target = {
          id: edgeData.dest_node,
          color: getCategoryColorValue(),
          category: "",
          expand: false,
          visible: true,
          collapsed,
          isPath: !!path,
          isPathSelected: path?.start?.id === edgeData.dest_node || path?.end?.id === edgeData.dest_node,
          data: {
            name: edgeData.dest_node
          }
        }
        this.nodesMap.set(edgeData.dest_node, target)
        this.elements.nodes.push(target)
        newElements.nodes.push(target)
      }

      let label = this.labelsMap.get(edgeData.relation)
      if (!label) {
        label = { name: edgeData.relation }
        this.labelsMap.set(edgeData.relation, label)
        this.labels.push(label)
      }

      link = {
        id: edgeData.id,
        source: edgeData.src_node,
        target: edgeData.dest_node,
        label: edgeData.relation,
        visible: true,
        collapsed,
        color: "#999999",
        isPathSelected: false,
        isPath: !!path,
        data: { ...edgeData.properties }
      }

      this.linksMap.set(edgeData.id, link)
      this.elements.links.push(link)
      newElements.links.push(link)
    })

    return newElements
  }

  public removeLinks(ids: number[] = []) {
    this.elements.links = this.elements.links.filter(link => {
      const isConnectedToIds = ids.length !== 0 && (ids.includes(link.source) || ids.includes(link.target))
      const hasEndpoints = this.nodesMap.get(link.source) && this.nodesMap.get(link.target)
      const shouldKeep = Boolean(hasEndpoints) && !(link.collapsed && isConnectedToIds)

      if (!shouldKeep) {
        this.linksMap.delete(link.id)
      }

      return shouldKeep
    })
  }

  public visibleLinks(visible: boolean, ids?: number[]) {
    const elements = ids ? this.elements.links.filter(link => ids.includes(link.source) || ids.includes(link.target)) : this.elements.links

    elements.forEach(link => {
      if (visible && this.nodesMap.get(link.source)?.visible && this.nodesMap.get(link.target)?.visible) {
        // eslint-disable-next-line no-param-reassign
        link.visible = true
      }

      if (!visible && (this.nodesMap.get(link.source)?.visible === false || this.nodesMap.get(link.target)?.visible === false)) {
        // eslint-disable-next-line no-param-reassign
        link.visible = false
      }
    })
  }
}