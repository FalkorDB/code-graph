export interface Category {
  name: string,
  index: number
}

export interface Node {
  id: string,
  name: string,
  value: any,
  color: string,
}

export interface Edge {
  source: number,
  target: number,
  label: string,
  value: any,
}

const COLORS = [
  "#FF6D60", // Red
  "#F7D060", // Yellow
  "#98D8AA", // Green
]

export class Graph {

  private id: string;
  private categories: Category[];
  private elements: any[];

  private categoriesMap: Map<String, Category>;
  private nodesMap: Map<number, Node>;
  private edgesMap: Map<number, Edge>;

  private constructor(id: string, categories: Category[], elements: any[],
    categoriesMap: Map<String, Category>, nodesMap: Map<number, Node>, edgesMap: Map<number, Edge>
  ) {
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

  public static empty(): Graph{
    return new Graph("", [], [], new Map<String, Category>(), new Map<number, Node>(), new Map<number, Edge>())
  }

  public static create(results: any | null): Graph {
    let graph = Graph.empty()
    graph.extend(results)
    graph.id = results.id
    return graph
  }

  public extend(results: any | null) {
    results.nodes.forEach((nodeData: any) => {
      let label = nodeData.labels[0]
      // check if category already exists in categories
      let category = this.categoriesMap.get(label)
      if (!category) {
        category = { name: label, index: this.categoriesMap.size }
        this.categoriesMap.set(label, category)
      }

      // check if node already exists in nodes or fake node was created
      let node = this.nodesMap.get(nodeData.id)
      if (!node) {
        node = {
          id: nodeData.id.toString(),
          name: nodeData.properties.name,
          value: JSON.stringify(nodeData.properties),
          color: category.index<COLORS.length ? COLORS[category.index] : COLORS[0]
        }
        this.nodesMap.set(nodeData.id, node)
      }
    })

    results.edges.forEach((edgeData: any) => {
      let edgeId = this.edgesMap.get(edgeData.id)
      if(edgeId){
        return
      }

      let sourceId = edgeData.sourceId.toString();
      let destinationId = edgeData.destinationId.toString()
      this.edgesMap.set(edgeData.id, {
        source: sourceId, 
        target: destinationId, 
        label: edgeData.relationshipType,
        value: JSON.stringify(edgeData.properties),
      })

      // creates a fakeS node for the source and target
      let source = this.nodesMap.get(edgeData.sourceId)
      if (!source) {
        source = { id: sourceId, name: sourceId, value: "", color: COLORS[0] }
        this.nodesMap.set(edgeData.sourceId, source)
      }

      let destination = this.nodesMap.get(edgeData.destinationId)
      if (!destination) {
        destination = { id: destinationId, name: destinationId, value: "", color: COLORS[0] }
        this.nodesMap.set(edgeData.destinationId, destination)
      }
    })

    this.categories = new Array<Category>()
    this.categoriesMap.forEach((category) => {
      this.categories[category.index] = category
    })

    this.elements = new Array<Node>()
    this.nodesMap.forEach((node) => {
      this.elements.push({data:node})
    })
    this.edgesMap.forEach((edge) => {
      this.elements.push({data:edge})
    })
  }
}


