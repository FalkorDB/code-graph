import CytoscapeComponent from 'react-cytoscapejs'
import { Dispatch, MutableRefObject, SetStateAction, useContext, useEffect, useRef, useState } from "react";
import { Node } from "./model";
import { GraphContext } from "./provider";
import cytoscape, { ElementDefinition, EventObject, Position } from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { GitFork, Search, X } from "lucide-react";
import ElementMenu from "./elementMenu";
import ElementTooltip from "./elementTooltip";
import Combobox from "./combobox";
import { toast } from '@/components/ui/use-toast';
import { Path } from '../page';
import Input from './Input';
import CommitList from './commitList';
import { Checkbox } from '@/components/ui/checkbox';

interface Props {
    onFetchGraph: (graphName: string) => void,
    onFetchNode: (node: Node) => Promise<any[]>,
    options: string[]
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    chartRef: MutableRefObject<cytoscape.Core | null>
    selectedValue: string
    setSelectedPathId: (selectedPathId: string) => void
    isPathResponse: boolean
    setIsPathResponse: Dispatch<SetStateAction<boolean>>
}

// The stylesheet for the graph
const STYLESHEET: cytoscape.Stylesheet[] = [
    {
        selector: "core",
        style: {
            'active-bg-size': 0,  // hide gray circle when panning
            // All of the following styles are meaningless and are specified
            // to satisfy the linter...
            'active-bg-color': 'blue',
            'active-bg-opacity': 0.3,
            "selection-box-border-color": 'blue',
            "selection-box-border-width": 0,
            "selection-box-opacity": 1,
            "selection-box-color": 'blue',
            "outside-texture-bg-color": 'blue',
            "outside-texture-bg-opacity": 1,
        },
    },
    {
        selector: "node",
        style: {
            label: "data(name)",
            "color": "black",
            "text-valign": "center",
            "text-wrap": "ellipsis",
            "text-max-width": "10rem",
            shape: "ellipse",
            height: "15rem",
            width: "15rem",
            "border-width": 0.3,
            "border-color": "black",
            "border-opacity": 0.5,
            "background-color": "data(color)",
            "font-size": "3rem",
            "overlay-padding": "1rem",
        },
    },
    {
        selector: "node:active",
        style: {
            "overlay-opacity": 0,  // hide gray box around active node
        },
    },
    {
        selector: "node:selected",
        style: {
            'border-width': 0.5,
            'border-color': 'black',
            'border-opacity': 1,
        },
    },
    {
        selector: "edge",
        style: {
            width: 0.5,
            "line-color": "#ccc",
            "arrow-scale": 0.3,
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#ccc",
            label: "data(label)",
            'curve-style': 'straight',
            "text-background-color": "#ffffff",
            "text-background-opacity": 1,
            "font-size": "3",
            "overlay-padding": "2px",
        },
    },
    {
        selector: "edge:active",
        style: {
            "overlay-opacity": 0,  // hide gray box around active node
        },
    }
]

cytoscape.use(fcose);

export const LAYOUT = {
    name: "fcose",
    fit: true,
    padding: 80,
    avoidOverlap: true,
}

export function CodeGraph({
    onFetchGraph,
    onFetchNode,
    options,
    isShowPath,
    setPath,
    chartRef,
    selectedValue,
    setSelectedPathId,
    isPathResponse,
    setIsPathResponse
}: Props) {

    let graph = useContext(GraphContext)

    const [url, setURL] = useState("");
    const [selectedObj, setSelectedObj] = useState<Node>();
    const [tooltipLabel, setTooltipLabel] = useState<string>();
    const [position, setPosition] = useState<Position>();
    const [tooltipPosition, setTooltipPosition] = useState<Position>();
    const [graphName, setGraphName] = useState<string>("");
    const [searchNodeName, setSearchNodeName] = useState<string>("");
    const [commits, setCommits] = useState<any[]>([]);
    const [nodesCount, setNodesCount] = useState<number>(0);
    const [edgesCount, setEdgesCount] = useState<number>(0);
    const [commitIndex, setCommitIndex] = useState<number>(0);
    const [currentCommit, setCurrentCommit] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);

    async function fetchCount() {
        const result = await fetch(`/api/repo/${graphName}`, {
            method: 'POST'
        })

        if (!result.ok) {
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: await result.text(),
            })
            return
        }

        const json = await result.json()

        setNodesCount(json.result.info.node_count)
        setEdgesCount(json.result.info.edge_count)
        setURL(json.result.info.repo_url)
    }

    useEffect(() => {
        if (!selectedValue) return
        handelSelectedValue(selectedValue)
    }, [selectedValue])

    useEffect(() => {
        if (!graphName) return

        const run = async () => {
            fetchCount()
            const result = await fetch(`/api/repo/${graphName}/?type=commit`, {
                method: 'POST'
            })

            if (!result.ok) {
                toast({
                    variant: "destructive",
                    title: "Uh oh! Something went wrong.",
                    description: await result.text(),
                })
                return
            }

            const json = await result.json()
            const commitsArr = json.result.commits
            setCommits(commitsArr)
            setCurrentCommit(commitsArr[commitsArr.length - 1].hash)
            setCommitIndex(commitsArr.length)
        }

        run()
    }, [graphName])

    function handelSelectedValue(value: string) {
        setGraphName(value)
        onFetchGraph(value)
    }

    function onCategoryClick(name: string, show: boolean) {
        let chart = chartRef.current
        if (chart) {
            let elements = chart.elements(`node[category = "${name}"]`)

            graph.Categories.forEach((category) => {
                if (category.name === name) {
                    category.show = show
                }
            })

            if (show) {
                elements.style({ display: 'element' })
            } else {
                elements.style({ display: 'none' })
            }
            chart.elements().layout(LAYOUT).run();
        }
    }

    const deleteNeighbors = (node: Node, chart: cytoscape.Core) => {
        const neighbors = chart.elements(`#${node.id}`).outgoers()
        neighbors.forEach((n) => {
            const id = n.id()
            const index = graph.Elements.findIndex(e => e.data.id === id);
            const element = graph.Elements[index]

            if (index === -1 || !element.data.collapsed) return

            const type = "category" in element.data

            if (element.data.expand) {
                deleteNeighbors(element.data, chart)
            }

            graph.Elements.splice(index, 1);

            if (type) {
                graph.NodesMap.delete(Number(id))
            } else {
                graph.EdgesMap.delete(Number(id.split('_')[1]))
            }

            chart.remove(`#${id}`)
        })

    }

    const handleDoubleTap = async (evt?: EventObject) => {

        const chart = chartRef.current

        if (!chart) return

        let node: Node
        let elements: ElementDefinition[]

        if (evt) {
            const { target } = evt
            target.unselect()
            node = target.json().data;
        } else {
            node = selectedObj!
        }

        const graphNode = graph.Elements.find(e => e.data.id === node.id);

        if (!graphNode) return

        if (!graphNode.data.expand) {
            elements = await onFetchNode(node)
            console.log(elements);
            if (elements.length === 0) {
                toast({
                    title: "No neighbors found",
                })
                return
            }

            chart.add(elements);
        } else {
            deleteNeighbors(node, chart)
        }

        graphNode.data.expand = !graphNode.data.expand;
        setSelectedObj(undefined)
        chart.elements().layout(LAYOUT).run();
    }

    const handelTap = (evt: EventObject) => {
        const chart = chartRef.current

        if (!chart) return

        const { target } = evt
        setTooltipLabel(undefined)

        if (isShowPath) {
            setPath(prev => {
                if (!prev?.start?.name || (prev.end?.name && prev.end?.name !== "")) {
                    return ({ start: { id: Number(target.id()), name: target.data().name as string } })
                } else {
                    return ({ end: { id: Number(target.id()), name: target.data().name as string }, start: prev.start })
                }
            })
            return
        }

        const position = target.renderedPosition()
        setPosition(() => position ? { x: position.x, y: position.y + chart.zoom() * 8 } : { x: 0, y: 0 });
        setSelectedObj(target.json().data)
    }

    const handelSearchSubmit = (node: any) => {
        const chart = chartRef.current

        if (!chart) return

        let chartNode = chart.elements(`node[name = "${node.properties.name}"]`)

        if (chartNode.length === 0) {
            const [newNode] = graph.extend({ nodes: [node], edges: [] })
            chartNode = chart.add(newNode)
        }

        chartNode.select()
        const layout = { ...LAYOUT, padding: 250 }
        chartNode.layout(layout).run()
        setSearchNodeName("")
    }

    return (
        <div ref={containerRef} className="h-full w-full flex flex-col gap-4 p-8 bg-gray-100">
            <header className="flex flex-col gap-4">
                <Combobox
                    options={options}
                    selectedValue={graphName}
                    onSelectedValue={handelSelectedValue}
                />
            </header>
            <div className='h-1 grow flex flex-col'>

                <main className="bg-white h-1 grow">
                    {
                        graph.Id ?
                            <div className="h-full relative border">
                                <div className="w-full absolute top-0 left-0 flex justify-between p-4 z-10 pointer-events-none">
                                    <div className='flex gap-4 pointer-events-auto'>
                                        <Input
                                            graph={graph}
                                            value={searchNodeName}
                                            onValueChange={(node) => setSearchNodeName(node.name!)}
                                            icon={<Search />}
                                            handelSubmit={handelSearchSubmit}
                                        />
                                        <Labels categories={graph.Categories} onClick={onCategoryClick} />
                                    </div>
                                    {
                                        isPathResponse &&
                                        <button
                                            className='bg-[#ECECEC] hover:bg-[#D3D3D3] p-2 rounded-md flex gap-2 items-center pointer-events-auto'
                                            onClick={() => {
                                                chartRef.current?.elements().removeStyle().layout(LAYOUT).run()
                                                setIsPathResponse(false)
                                            }}
                                        >
                                            <X size={15} />
                                            <p>Clear Graph</p>
                                        </button>
                                    }
                                </div>
                                <div className="w-full absolute bottom-0 left-0 flex justify-between items-center p-4 z-10 pointer-events-none">
                                    <div className="flex gap-4 text-gray-500">
                                        <p>{nodesCount} Nodes</p>
                                        <p>{edgesCount} Edges</p>
                                    </div>
                                    <div className='flex gap-4'>
                                        {/* <div className='bg-white flex gap-2 border rounded-md p-2 pointer-events-auto'>
                                            <div className='flex gap-2 items-center'>
                                                <Checkbox
                                                    className='h-5 w-5 bg-gray-500 data-[state true]'
                                                />
                                                <p className='text-bold'>Display Changes</p>
                                            </div>
                                            <div className='flex gap-2 items-center'>
                                                <div className='h-4 w-4 bg-pink-500 bg-opacity-50 border-[3px] border-pink-500 rounded-full'/>
                                                <p className='text-pink-500'>Were added</p>
                                            </div>
                                            <div className='flex gap-2 items-center'>
                                                <div className='h-4 w-4 bg-blue-500 bg-opacity-50 border-[3px] border-blue-500 rounded-full'/>
                                                <p className='text-blue-500'>Were edited</p>
                                            </div>
                                        </div> */}
                                        <Toolbar className="pointer-events-auto" chartRef={chartRef} />
                                    </div>
                                </div>
                                <ElementTooltip
                                    label={tooltipLabel}
                                    position={tooltipPosition}
                                    parentWidth={containerRef.current?.clientWidth || 0}
                                />
                                <ElementMenu
                                    obj={selectedObj}
                                    position={position}
                                    url={url}
                                    handelMaximize={handleDoubleTap}
                                    parentWidth={containerRef.current?.clientWidth || 0}
                                />
                                <CytoscapeComponent
                                    cy={(cy) => {
                                        chartRef.current = cy

                                        // Make sure no previous listeners are attached
                                        cy.removeAllListeners();

                                        // Listen to the click event on nodes for expanding the node
                                        cy.on('dbltap', 'node', handleDoubleTap);

                                        cy.on('mousedown', (evt) => {
                                            setTooltipLabel(undefined)
                                            const { target } = evt

                                            if (target !== cy && !target.isEdge()) return;

                                            setSelectedObj(undefined)
                                        })

                                        cy.on('mouseout', (evt) => {
                                            const { target } = evt

                                            if (target === cy || target.isEdge()) {
                                                setTooltipLabel(undefined)
                                                return
                                            }

                                            setTooltipLabel(undefined)

                                            if (selectedObj) return

                                            target.unselect()
                                        })

                                        cy.on('scrollzoom', () => {
                                            setSelectedObj(undefined)
                                            setTooltipLabel(undefined)
                                        });

                                        cy.on('mouseover', 'node', (evt) => {
                                            const { target } = evt
                                            target.select()

                                            if (selectedObj) return

                                            const position = target.renderedPosition()

                                            setTooltipPosition(() => ({ x: position.x, y: position.y + cy.zoom() * 8 }));
                                            setTooltipLabel(() => target.json().data.name);
                                        })

                                        cy.on('tap', 'node', handelTap);

                                        cy.on('drag', 'node', () => {
                                            setTooltipLabel(undefined)
                                            setSelectedObj(undefined)
                                        });

                                        cy.on('tap', 'edge', (evt) => {
                                            const { target } = evt

                                            if (!isPathResponse) return

                                            setSelectedPathId(target.id())
                                        });
                                    }}
                                    stylesheet={STYLESHEET}
                                    elements={graph.Elements}
                                    layout={LAYOUT}
                                    className="h-full w-full"
                                />
                            </div>
                            : <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                <GitFork size={100} color="gray" />
                                <h1 className="text-4xl">Select a repo to show its graph here</h1>
                            </div>
                    }
                </main>
                {
                    graph.Id &&
                    <CommitList
                        commitIndex={commitIndex}
                        commits={commits}
                        currentCommit={currentCommit}
                        setCommitIndex={setCommitIndex}
                        setCurrentCommit={setCurrentCommit}
                        graph={graph}
                        chartRef={chartRef}
                    />
                }
            </div>
        </div>
    )
}