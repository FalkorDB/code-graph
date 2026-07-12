import { Dispatch, SetStateAction, useEffect, useRef, useState } from "react";
import { Graph, GraphData, Node } from "./model";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { Download, GitFork, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import ElementMenu from "./elementMenu";
import Combobox from "./combobox";
import { toast } from '@/components/ui/use-toast';
import { Path, RepoOption } from "@/lib/utils";
import Input from './Input';
// import CommitList from './commitList';
import { Checkbox } from '@/components/ui/checkbox';
import type { Position } from "./graphView";
import { GraphRef } from "@/lib/utils";
import GraphView from "./graphView";
import { convertToCanvasData } from "./ForceGraph";

const AUTH_HEADERS: HeadersInit = import.meta.env.VITE_SECRET_TOKEN
    ? { 'Authorization': `Bearer ${import.meta.env.VITE_SECRET_TOKEN}` }
    : {};

interface Props {
    id: "desktop" | "mobile"
    graph: Graph,
    data: GraphData,
    setData: Dispatch<SetStateAction<GraphData>>,
    onFetchGraph: (graphName: string) => Promise<void>,
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>,
    options: RepoOption[]
    setOptions: Dispatch<SetStateAction<RepoOption[]>>
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    canvasRef: GraphRef
    selectedValue: string
    selectedPathId: number | undefined
    setSelectedPathId: (selectedPathId: number) => void
    isPathResponse: boolean | undefined
    setIsPathResponse: Dispatch<SetStateAction<boolean | undefined>>
    handleSearchSubmit: (node: any) => void
    searchNode: any
    setSearchNode: Dispatch<SetStateAction<any>>
    animation: boolean
    setAnimation: (animation: boolean) => void
    manualDimmed: boolean
    setManualDimmed: (dimmed: boolean) => void
    onCategoryClick: (name: string, show: boolean) => void
    handleDownloadImage: () => void
    zoomedNodes: Node[]
    setZoomedNodes: Dispatch<SetStateAction<Node[]>>
    hasHiddenElements: boolean
    setHasHiddenElements: Dispatch<SetStateAction<boolean>>
}

export function CodeGraph({
    id,
    graph,
    data,
    setData,
    onFetchGraph,
    onFetchNode,
    options,
    setOptions,
    isShowPath,
    setPath,
    canvasRef,
    selectedValue,
    setSelectedPathId,
    isPathResponse,
    setIsPathResponse,
    selectedPathId,
    handleSearchSubmit,
    searchNode,
    setSearchNode,
    animation,
    setAnimation,
    manualDimmed,
    setManualDimmed,
    onCategoryClick,
    handleDownloadImage,
    zoomedNodes,
    setZoomedNodes,
    hasHiddenElements,
    setHasHiddenElements
}: Props) {

    const [url, setURL] = useState("");
    const [selectedObjects, setSelectedObjects] = useState<Node[]>([]);
    const [position, setPosition] = useState<Position>();
    const [graphName, setGraphName] = useState<string>("");
    const [commits, setCommits] = useState<any[]>([]);
    const [nodesCount, setNodesCount] = useState<number>(0);
    const [edgesCount, setEdgesCount] = useState<number>(0);
    const [commitIndex, setCommitIndex] = useState<number>(0);
    const [currentCommit, setCurrentCommit] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        setData({ ...graph.Elements })
    }, [graph.Id])

    useEffect(() => {
        if (!selectedValue) return
        handleSelectedValue(selectedValue)
    }, [selectedValue])

    useEffect(() => {
        setHasHiddenElements(graph.getElements().some(element => !element.visible))
    }, [data, graph.Id])

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Delete') {
                if (selectedObjects.length === 0) return

                handleRemove(selectedObjects.map(obj => obj.id), "nodes");
            }
        };

        document.addEventListener('keydown', handleKeyDown);

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [selectedObjects]);

    async function fetchCount() {
        const result = await fetch(`/api/repo_info`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...AUTH_HEADERS,
            },
            body: JSON.stringify({ repo: graphName }),
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

        setNodesCount(json.info.node_count)
        setEdgesCount(json.info.edge_count)
        setURL(json.info.repo_url)
    }

    useEffect(() => {
        if (!graphName) return

        const run = async () => {
            fetchCount()
            /*
            const result = await fetch(`/api/repo/${prepareArg(graphName)}/commit`, {
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
            const commitsArr = json.commits
            setCommits(commitsArr)

            if (commitsArr.length > 0) {
                setCurrentCommit(commitsArr[commitsArr.length - 1].hash)
                setCommitIndex(commitsArr.length)
            }
            */
        }

        run()

    }, [graphName])

    async function handleSelectedValue(value: string) {
        setGraphName(value)
        await onFetchGraph(value)
    }

    const deleteNeighbors = (nodes: Node[]) => {

        if (nodes.length === 0) return;

        const expandedNodes: Node[] = []

        graph.Elements = {
            nodes: graph.Elements.nodes.filter(node => {
                if (!node.collapsed) return true

                // Check if this collapsed node is directly part of any link from deleted nodes
                const isConnected = graph.Elements.links.some(link => 
                    (link.target === node.id && nodes.some(n => n.id === link.source)) ||
                    (link.source === node.id && nodes.some(n => n.id === link.target))
                );

                if (!isConnected) return true

                if (graph.NodesMap.delete(Number(node.id)) && node.expand) {
                    expandedNodes.push(node)
                }

                return false
            }),
            links: graph.Elements.links
        }

        deleteNeighbors(expandedNodes)

        graph.removeLinks(nodes.map(n => n.id))
    }

    const handleExpand = async (nodes: Node[], expand: boolean) => {
        if (expand) {
            // DON'T set expand state until after successful fetch
            const elements = await onFetchNode(nodes.map(n => n.id))

            if (elements.nodes.length === 0) {
                toast({
                    title: `No neighbors found`,
                    description: `No neighbors found`,
                })
                // Don't set expand if no neighbors found - no glow effect
                return
            }

            // Only NOW set expand state after successful fetch - glow animation triggers here
            nodes.forEach((node) => {
                node.expand = true
            })

            // Update the model with new elements (graph.Elements is already updated by onFetchNode)
            // Convert the full model to canvas data and update
            canvasRef.current?.setGraphData(convertToCanvasData(graph.Elements))
            setData({ ...graph.Elements })
        } else {
            const deleteNodes = nodes.filter(n => n.expand)
            if (deleteNodes.length > 0) {
                deleteNeighbors(deleteNodes)
            }

            // Set expand state AFTER deleteNeighbors so the filter above works
            nodes.forEach((node) => {
                node.expand = false
            })

            // Convert the updated model to canvas data
            canvasRef.current?.setGraphData(convertToCanvasData(graph.Elements))
            setData({ ...graph.Elements })
        }

        setSelectedObjects([])
    }

    const handleRemove = (ids: number[], type: "nodes" | "links") => {
        const canvas = canvasRef.current

        if (!canvas) return

        graph.Elements[type].forEach(element => {
            if (!ids.includes(element.id)) return
            element.visible = false
        })

        if (type === "nodes") {
            graph.visibleLinks(false, ids)
        }

        // setGraphData doesn't update visible for existing nodes — mutate canvas nodes directly
        const canvasData = canvas.getGraphData()
        canvasData.nodes.forEach(canvasNode => {
            const appNode = graph.NodesMap.get(canvasNode.id)
            if (appNode) canvasNode.visible = appNode.visible
        })
        canvasData.links.forEach(canvasLink => {
            const appLink = graph.LinksMap.get(canvasLink.id)
            if (appLink) canvasLink.visible = appLink.visible
        })
        canvas.refresh()

        setData({ ...graph.Elements })
        setHasHiddenElements(true)

        setSelectedObjects([])
    }

    return (
        <div className="grow md:h-full w-full flex flex-col gap-4 p-4 pt-0 md:p-8 md:bg-muted">
            <header className="flex flex-col gap-4 relative">
                <div className="absolute md:hidden inset-x-0 top-8 h-[50%] bg-muted -mx-8 -mt-8 px-8 border-b border-border" />
                <Combobox
                    options={options}
                    setOptions={setOptions}
                    selectedValue={graphName}
                    onSelectedValue={handleSelectedValue}
                />
            </header>
            <div className='h-1 grow flex flex-col'>
                <main ref={containerRef} className="bg-background h-1 grow">
                    {
                        graph.Id ?
                            <div className="h-full relative border flex flex-col md:block">
                                <div className="flex w-full absolute top-0 left-0 justify-between p-4 z-10 pointer-events-none">
                                    <div className='hidden md:flex gap-4'>
                                        <Input
                                            graph={graph}
                                            onValueChange={(node) => setSearchNode(node)}
                                            icon={<Search />}
                                            handleSubmit={(node) => {
                                                handleSearchSubmit(node)
                                            }}
                                            node={searchNode}
                                        />
                                        <Labels categories={graph.Categories} onClick={onCategoryClick} />
                                    </div>
                                    <div className="flex gap-2">
                                        {
                                            (isPathResponse || isPathResponse === undefined) &&
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                className='pointer-events-auto'
                                                onClick={() => {
                                                    const canvas = canvasRef.current

                                                    if (!canvas) return

                                                    // Clear path flags from graph model
                                                    graph.Elements.nodes.forEach((node) => {
                                                        node.isPath = false
                                                        node.isPathSelected = false
                                                    })

                                                    graph.Elements.links.forEach((link) => {
                                                        link.isPath = false
                                                        link.isPathSelected = false
                                                        link.color = "#999999"  // Reset link color
                                                    })

                                                    // Update React state to trigger re-render
                                                    setData({ ...graph.Elements })

                                                    // Update canvas
                                                    canvas.setGraphData(convertToCanvasData(graph.Elements))
                                                    canvas.zoomToFit()
                                                    setIsPathResponse(false)
                                                }}
                                            >
                                                <X size={15} />
                                                Reset Graph
                                            </Button>
                                        }
                                        {
                                            hasHiddenElements &&
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                className='pointer-events-auto'
                                                onClick={() => {
                                                    const canvas = canvasRef.current;

                                                    if (!canvas) return;

                                                    graph.Categories.forEach(c => c.show = true);
                                                    graph.getElements().forEach((element) => {
                                                        element.visible = true
                                                    });

                                                    const canvasData = canvas.getGraphData();
                                                    canvasData.nodes.forEach((n: { visible: boolean }) => { n.visible = true; });
                                                    canvasData.links.forEach((l: { visible: boolean }) => { l.visible = true; });
                                                    canvas.refresh();
                                                    setData({ ...graph.Elements });
                                                    setHasHiddenElements(false);
                                                }}
                                            >
                                                <X size={15} />
                                                Unhide Nodes
                                            </Button>
                                        }
                                    </div>
                                </div>
                                <ElementMenu
                                    obj={selectedObjects[0]}
                                    objects={selectedObjects}
                                    setPath={(path) => {
                                        setPath(path)
                                        setSelectedObjects([])
                                    }}
                                    handleRemove={handleRemove}
                                    position={position}
                                    url={url}
                                    handleExpand={handleExpand}
                                    parentRef={containerRef}
                                />
                                <GraphView
                                    id={id}
                                    data={data}
                                    setData={setData}
                                    graph={graph}
                                    chartRef={canvasRef}
                                    selectedObjects={selectedObjects}
                                    setSelectedObjects={setSelectedObjects}
                                    setPosition={setPosition}
                                    handleExpand={handleExpand}
                                    isShowPath={isShowPath}
                                    setPath={setPath}
                                    isPathResponse={isPathResponse}
                                    selectedPathId={selectedPathId}
                                    setSelectedPathId={setSelectedPathId}
                                    setZoomedNodes={setZoomedNodes}
                                    zoomedNodes={zoomedNodes}
                                    manualDimmed={manualDimmed}
                                />
                                <div data-name="canvas-info-panel" className="w-full md:absolute md:bottom-0 md:left-0 md:flex md:justify-between md:items-center md:p-4 z-10 pointer-events-none">
                                    <div data-name="metrics-panel" className="flex gap-4 justify-center bg-muted md:bg-transparent md:text-muted-foreground p-2 md:p-0">
                                        <p>{nodesCount} Nodes</p>
                                        <p className="md:hidden">|</p>
                                        <p>{edgesCount} Edges</p>
                                    </div>
                                    <div className='hidden md:flex gap-4'>
                                        {
                                            commitIndex !== commits.length &&
                                            <div className='bg-background flex gap-2 border rounded-md p-2 pointer-events-auto'>
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
                                            className="gap-4"
                                            canvasRef={canvasRef}
                                            handleDownloadImage={handleDownloadImage}
                                            animation={animation}
                                            setAnimation={setAnimation}
                                            manualDimmed={manualDimmed}
                                            setManualDimmed={setManualDimmed}
                                            selectedObjects={selectedObjects}
                                        />
                                    </div>
                                </div>
                            </div>
                            : <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                <GitFork className="md:w-24 md:h-24 w-16 h-16" />
                                <h1 className="md:text-4xl text-2xl text-center">Select a repo to show its graph here</h1>
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
