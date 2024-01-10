export interface Category {
  name: string,
  index: number
}

export interface Node {
  id: string,
  name: string,
  value: any,
  category: number,
}

export interface Edge {
  source: number,
  target: number,
  relationshipType: string,
  value: any,
}

export class Graph {

  private id: string;
  private categories: Category[];
  private nodes: Node[];
  private edges: Edge[];

  private categoriesMap: Map<String, Category>;
  private nodesMap: Map<number, Node>;
  private edgesSet: Set<Edge>;

  private constructor(id: string, categories: Category[], nodes: Node[], edges: Edge[],
    categoriesMap: Map<String, Category>, nodesMap: Map<number, Node>, edgesSet: Set<Edge>
  ) {
    this.id = id;
    this.categories = categories;
    this.nodes = nodes;
    this.edges = edges;
    this.categoriesMap = categoriesMap;
    this.nodesMap = nodesMap;
    this.edgesSet = edgesSet;
  }

  get Id(): string {
    return this.id;
  }

  get Categories(): Category[] {
    return this.categories;
  }

  get Nodes(): Node[] {
    return this.nodes;
  }

  get Edges(): Edge[] {
    return this.edges;
  }

  public static empty(): Graph{
    return new Graph("", [], [], [], new Map<String, Category>(), new Map<number, Node>(), new Set<Edge>())
  }

  public static create(results: any | null): Graph{
    let graph = Graph.empty()
    graph.extend(results)
    graph.id = results.id
    return graph
  }

  public extend(results: any | null) {

    results.nodes.forEach((row: any) => {

      let nodeData = row.n;
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
          category: category.index
        }
        this.nodesMap.set(nodeData.id, node)
      }
    })

    results.edges.forEach((row: any) => {
      let edgeData = row.e;

      let sourceId = edgeData.sourceId.toString();
      let destinationId = edgeData.destinationId.toString()
      this.edgesSet.add({
        source: sourceId, 
        target: destinationId, 
        relationshipType: edgeData.relationshipType,
        value: JSON.stringify(edgeData.properties),
      })

      // creates a fakeS node for the source and target
      let source = this.nodesMap.get(edgeData.sourceId)
      if (!source) {
        source = { id: sourceId, name: sourceId, value: "", category: 0 }
        this.nodesMap.set(edgeData.sourceId, source)
      }

      let destination = this.nodesMap.get(edgeData.destinationId)
      if (!destination) {
        destination = { id: destinationId, name: destinationId, value: "", category: 0 }
        this.nodesMap.set(edgeData.destinationId, destination)
      }
    })

    this.categories = new Array<Category>()
    this.categoriesMap.forEach((category) => {
      this.categories[category.index] = category
    })

    this.nodes = new Array<Node>()
    this.nodesMap.forEach((node) => {
      this.nodes.push(node)
    })

    this.edges = new Array<Edge>()
    this.edgesSet.forEach((edge) => {
      this.edges.push(edge)
    })
  }
}


