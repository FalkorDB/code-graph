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
import { Path, PathNode } from '../page';
import Input from './Input';
import CommitList from './commitList';
import { Checkbox } from '@/components/ui/checkbox';

interface Props {
    onFetchGraph: (graphName: string) => void,
    onFetchNode: (nodeIds: string[]) => Promise<any[]>,
    options: string[]
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    chartRef: MutableRefObject<cytoscape.Core | null>
    selectedValue: string
    selectedPathId: string | undefined
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
            "selection-box-border-color": 'gray',
            "selection-box-border-width": 3,
            "selection-box-opacity": 0.5,
            "selection-box-color": 'gray',
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
    setIsPathResponse,
    selectedPathId
}: Props) {

    let graph = useContext(GraphContext)

    const [url, setURL] = useState("");
    const [selectedObj, setSelectedObj] = useState<Node>();
    const [selectedObjects, setSelectedObjects] = useState<Node[]>([]);
    const [isSelectedObj, setIsSelectedObj] = useState<string>("");
    const [tooltipLabel, setTooltipLabel] = useState<string>();
    const [position, setPosition] = useState<Position>();
    const [tooltipPosition, setTooltipPosition] = useState<Position>();
    const [graphName, setGraphName] = useState<string>("");
    const [searchNode, setSearchNode] = useState<PathNode>({});
    const [commits, setCommits] = useState<any[]>([]);
    const [nodesCount, setNodesCount] = useState<number>(0);
    const [edgesCount, setEdgesCount] = useState<number>(0);
    const [commitIndex, setCommitIndex] = useState<number>(0);
    const [currentCommit, setCurrentCommit] = useState(0);
    const [containerWidth, setContainerWidth] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        setContainerWidth(containerRef.current?.clientWidth || 0)
    }, [containerRef.current?.clientWidth])

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (!isSelectedObj && selectedObj && selectedObjects.length === 0) return

            if (event.key === 'Delete') {
                handelRemove(selectedObjects.length > 0 ? selectedObjects.map(obj => Number(obj.id)) : [Number(isSelectedObj || selectedObj?.id)]);
            }
        };

        document.addEventListener('keydown', handleKeyDown);

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [selectedObjects, selectedObj, isSelectedObj]);

    async function fetchCount() {
        const result = await fetch(`/api/repo/${graphName}/info`, {
            method: 'GET'
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
            /*
            const result = await fetch(`/api/repo/${graphName}/commit`, {
                method: 'GET'
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

            if (commitsArr.length > 0) {
                setCurrentCommit(commitsArr[commitsArr.length - 1].hash)
                setCommitIndex(commitsArr.length)
            }
            */
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

    const deleteNeighbors = (nodes: Node[], chart: cytoscape.Core) => {
        const neighbors = chart.elements(nodes.map(node => `#${node.id}`).join(',')).outgoers()
        neighbors.forEach((n) => {
            const id = n.id()
            const index = graph.Elements.findIndex(e => e.data.id === id);
            const element = graph.Elements[index]

            if (index === -1 || !element.data.collapsed) return

            const type = "category" in element.data

            if (element.data.expand) {
                deleteNeighbors([element.data], chart)
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
        if (evt) {
            const { target } = evt
            target.unselect()
            node = target.json().data
        } else {
            node = selectedObj!
        }

        const graphNode = graph.Elements.find(e => e.data.id === node.id)

        if (!graphNode) return

        const expand = !graphNode.data.expand

        if (expand) {
            const elements = await onFetchNode([node.id])

            if (elements.length === 0) {
                toast({
                    title: `No neighbors found`,
                    description: `No neighbors found`,
                })
                return
            }

            chart.add(elements);
        } else {
            deleteNeighbors([node], chart);
        }

        const element = chart.elements(`#${node.id}`)
        element.data('expand', expand)
        graphNode.data.expand = expand

        setSelectedObj(undefined)
        chart.elements().layout(LAYOUT).run();
    }

    const handleExpand = async (nodes: Node[], expand: boolean) => {

        const chart = chartRef.current

        if (!chart) return

        if (expand) {
            const elements = await onFetchNode(nodes.map(n => n.id))

            if (elements.length === 0) {
                toast({
                    title: `No neighbors found`,
                    description: `No neighbors found`,
                })
                return
            }

            chart.add(elements);
            chart.elements().layout(LAYOUT).run();
        } else {
            const deleteNodes = nodes.filter(n => n.expand === true)
            if (deleteNodes.length > 0) {
                deleteNeighbors(deleteNodes, chart);
                chart.elements().layout(LAYOUT).run();
            }
        }

        nodes.forEach((node) => {
            const graphNode = graph.Elements.find(e => e.data.id === node.id)
            const element = chart.elements(`#${node.id}`)

            if (!graphNode) return

            element.data("expand", expand)
            graphNode.data.expand = expand
        })

        setSelectedObj(undefined)
    }

    const handelSearchSubmit = (node: any) => {
        const chart = chartRef.current

        if (!chart) return

        const n = { name: node.properties.name, id: node.id }

        let chartNode = chart.elements(`node[id = "${n.id}"]`)

        if (chartNode.length === 0) {
            const [newNode] = graph.extend({ nodes: [node], edges: [] })
            chartNode = chart.add(newNode)
        }

        chartNode.select()
        chartNode.style({ display: "element" })
        setIsSelectedObj(String(n.id))
        const layout = { ...LAYOUT, padding: 250 }
        chartNode.layout(layout).run()
        setSearchNode(n)
    }

    const handelRemove = (ids: number[]) => {
        chartRef.current?.elements(`#${ids.join(',#')}`).style({ display: 'none' })
        if (ids.some(id => Number(selectedObj?.id) === id)) {
            setSelectedObj(undefined)
        }
    }

    return (
        <div className="h-full w-full flex flex-col gap-4 p-8 bg-gray-100">
            <header className="flex flex-col gap-4">
                <Combobox
                    options={options}
                    selectedValue={graphName}
                    onSelectedValue={handelSelectedValue}
                />
            </header>
            <div className='h-1 grow flex flex-col'>
                <main ref={containerRef} className="bg-white h-1 grow">
                    {
                        graph.Id ?
                            <div className="h-full relative border">
                                <div className="w-full absolute top-0 left-0 flex justify-between p-4 z-10 pointer-events-none">
                                    <div className='flex gap-4'>
                                        <Input
                                            graph={graph}
                                            value={searchNode.name}
                                            onValueChange={({ name }) => setSearchNode({ name })}
                                            icon={<Search />}
                                            handelSubmit={handelSearchSubmit}
                                            node={searchNode}
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
                                        {
                                            commitIndex !== commits.length &&
                                            <div className='bg-white flex gap-2 border rounded-md p-2 pointer-events-auto'>
                                                <div className='flex gap-2 items-center'>
                                                    <Checkbox
                                                        className='h-5 w-5 bg-gray-500 data-[state true]'
                                                    />
                                                    <p className='text-bold'>Display Changes</p>
                                                </div>
                                                <div className='flex gap-2 items-center'>
                                                    <div className='h-4 w-4 bg-pink-500 bg-opacity-50 border-[3px] border-pink-500 rounded-full' />
                                                    <p className='text-pink-500'>Were added</p>
                                                </div>
                                                <div className='flex gap-2 items-center'>
                                                    <div className='h-4 w-4 bg-blue-500 bg-opacity-50 border-[3px] border-blue-500 rounded-full' />
                                                    <p className='text-blue-500'>Were edited</p>
                                                </div>
                                            </div>
                                        }
                                        <Toolbar
                                            className="pointer-events-auto"
                                            chartRef={chartRef}
                                            setSelectedObj={setSelectedObj}
                                        />
                                    </div>
                                </div>
                                <ElementTooltip
                                    label={tooltipLabel}
                                    position={tooltipPosition}
                                    parentWidth={containerWidth}
                                />
                                <ElementMenu
                                    obj={selectedObj}
                                    objects={selectedObjects}
                                    setPath={(path) => {
                                        setPath(path)
                                        setSelectedObj(undefined)
                                    }}
                                    handelRemove={handelRemove}
                                    position={position}
                                    url={url}
                                    handelExpand={(nodes, expand) => {
                                        if (nodes && expand !== undefined) {
                                            handleExpand(nodes, expand)
                                        } else {
                                            handleDoubleTap()
                                        }
                                    }}
                                    parentWidth={containerWidth}
                                />
                                <CytoscapeComponent
                                    cy={(cy) => {
                                        chartRef.current = cy

                                        // Make sure no previous listeners are attached
                                        cy.removeAllListeners();

                                        // Listen to the click event on nodes for expanding the node
                                        cy.on('dbltap', 'node', handleDoubleTap);

                                        cy.on('mousedown', () => {
                                            setTooltipLabel(undefined)
                                            setSelectedObj(undefined)
                                            setIsSelectedObj("")
                                        })

                                        cy.on('mouseout', 'node', (evt) => {
                                            const { target } = evt

                                            setTooltipLabel(undefined)

                                            const { id } = target.json().data

                                            if (selectedObj?.id === id || isSelectedObj === id || selectedObjects.some(e => e.id === id)) return

                                            target.unselect()
                                        })

                                        cy.on('scrollzoom', () => {
                                            setSelectedObj(undefined)
                                            setTooltipLabel(undefined)
                                        });

                                        cy.on('mouseover', 'node', (evt) => {
                                            const { target } = evt

                                            target.select()

                                            if (selectedObj && target.id() === selectedObj.id) return

                                            const position = target.renderedPosition()

                                            setTooltipPosition(() => ({ x: position.x, y: position.y + cy.zoom() * 8 }));
                                            setTooltipLabel(() => target.json().data.name);
                                        })

                                        cy.on('tap', () => {
                                            setSelectedObjects([])
                                        })

                                        cy.on('tap', 'node', (evt) => {
                                            const { target } = evt

                                            target.select()

                                            setIsSelectedObj(target.json().data.id)

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
                                        });

                                        cy.on('cxttap', 'node', (evt) => {
                                            const chart = chartRef.current

                                            if (!chart) return

                                            setTooltipLabel(undefined)

                                            if (isSelectedObj && isSelectedObj !== evt.target.id()) {
                                                chart.elements(`#${isSelectedObj}`).unselect()
                                                setIsSelectedObj("")
                                            }

                                            if (selectedObj && selectedObj !== evt.target.id()) {
                                                chart.elements(`#${selectedObj.id}`).unselect()
                                            }

                                            const { target } = evt
                                            const { x, y } = target.renderedPosition()

                                            setPosition(() => (x && y) ? { x, y: y + chart.zoom() * 8 } : { x: 0, y: 0 });
                                            setSelectedObj(target.json().data)
                                        });

                                        cy.on('tap', 'edge', (evt) => {
                                            const { target } = evt

                                            if (!isPathResponse || selectedPathId === target.id()) return

                                            setSelectedPathId(target.id())
                                        });

                                        cy.on('boxselect', 'node', (evt) => {
                                            const { target } = evt

                                            selectedObjects.push(target.json().data)
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
                {/* {
                    graph.Id && commits.length > 0 &&
                    <CommitList
                        commitIndex={commitIndex}
                        commits={commits}
                        currentCommit={currentCommit}
                        setCommitIndex={setCommitIndex}
                        setCurrentCommit={setCurrentCommit}
                        graph={graph}
                        chartRef={chartRef}
                    />
                } */}
            </div>
        </div>
    )
}
