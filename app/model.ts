export interface Category {
  name: string,
  index: number
}

export interface Node {
  id: string,
  name: string,
  value: any,
  category: number,
  label: any,
}

export interface Edge {
  source: number,
  target: number,
  label: any,
}

export interface Graph {
  id: string,
  categories: Category[],
  nodes: Node[],
  edges: Edge[],
}

export function extractData(results: any | null): Graph {
  let categories = new Map<String, Category>()
  let nodes = new Map<number, Node>()

  results.nodes.forEach((row: any) => {

    let nodeData = row.n;
    let label = nodeData.labels[0]
    // check if category already exists in categories
    let category = categories.get(label)
    if (!category) {
      category = { name: label, index: categories.size }
      categories.set(label, category)
    }

    // check if node already exists in nodes or fake node was created
    let node = nodes.get(nodeData.id)
    if (!node) {
      node = { id: nodeData.id.toString(), name: nodeData.properties.name, value: JSON.stringify(nodeData.properties), category: category.index, label: { show: true } }
      nodes.set(nodeData.id, node)
    }
  })

  let edges = new Set<Edge>()
  results.edges.forEach((row: any) => {
    let edgeData = row.e;

    let sourceId = edgeData.sourceId.toString();
    let destinationId = edgeData.destinationId.toString()
    edges.add({
      source: sourceId, target: destinationId, label:
      {
        show: true,
        formatter: (params: any) => {
          return edgeData.relationshipType
        }
      }
    })

    // creates a fakeS node for the source and target
    let source = nodes.get(edgeData.sourceId)
    if (!source) {
      source = { id: sourceId, name: sourceId, value: "", category: 0, label: { show: true } }
      nodes.set(edgeData.sourceId, source)
    }

    let destination = nodes.get(edgeData.destinationId)
    if (!destination) {
      destination = { id: destinationId, name: destinationId, value: "", category: 0, label: { show: true } }
      nodes.set(edgeData.destinationId, destination)
    }
  })

  let categoriesArray = new Array<Category>()
  categories.forEach((category) => {
    categoriesArray[category.index] = category
  })

  let nodesArray = new Array<Node>()
  nodes.forEach((node) => {
    nodesArray.push(node)
  })

  let edgesArray = new Array<Edge>()
  edges.forEach((edge) => {
    edgesArray.push(edge)
  })

  return { id: results.id, categories: categoriesArray, nodes: nodesArray, edges: edgesArray }
}
