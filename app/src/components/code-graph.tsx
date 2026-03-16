import { Dispatch, SetStateAction, useEffect, useRef, useState } from "react";
import { Graph, GraphData, Node, Link } from "./model";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { GitFork, Loader2, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import ElementMenu from "./elementMenu";
import Combobox from "./combobox";
import { toast } from '@/components/ui/use-toast';
import { Path, PATH_COLOR } from "@/lib/utils";
import Input from './Input';
// import CommitList from './commitList';
import { Checkbox } from '@/components/ui/checkbox';
import type { Position } from "./graphView";
import { prepareArg } from '../utils';
import { GraphRef } from "@/lib/utils";
import { dataToGraphData } from "@falkordb/canvas";
import type { Node as CanvasNode, Link as CanvasLink, GraphData as CanvasData } from "@falkordb/canvas";
import GraphView from "./graphView";

const AUTH_HEADERS: HeadersInit = import.meta.env.VITE_SECRET_TOKEN
  ? { 'Authorization': `Bearer ${import.meta.env.VITE_SECRET_TOKEN}` }
  : {};

interface Props {
    id: "desktop" | "mobile"
    graph: Graph,
    data: GraphData,
    setData: Dispatch<SetStateAction<GraphData>>,
    onFetchGraph: (graphName: string) => Promise<void>,
    isFetchingGraph: boolean,
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>,
    options: string[]
    setOptions: Dispatch<SetStateAction<string[]>>
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
    cooldownTicks: number | undefined
    setCooldownTicks: Dispatch<SetStateAction<number | undefined>>
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
    isFetchingGraph,
    onFetchNode,
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
    cooldownTicks,
    setCooldownTicks,
    onCategoryClick,
    handleDownloadImage,
    zoomedNodes,
    setZoomedNodes,
    hasHiddenElements,
    setHasHiddenElements
}: Props) {

    const [url, setURL] = useState("");
    const [selectedObj, setSelectedObj] = useState<Node | Link>();
    const [selectedObjects, setSelectedObjects] = useState<Node[]>([]);
    const [position, setPosition] = useState<Position>();
    const [graphName, setGraphName] = useState<string>("");
    const [commits, setCommits] = useState<any[]>([]);
    const [nodesCount, setNodesCount] = useState<number>(0);
    const [edgesCount, setEdgesCount] = useState<number>(0);
    const [commitIndex, setCommitIndex] = useState<number>(0);
    const [currentCommit, setCurrentCommit] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);
    const [options, setOptions] = useState<string[]>([]);

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
                if (selectedObjects.length === 0 && (!selectedObj || "source" in selectedObj)) return
                
                handleRemove([...selectedObjects.map(obj => obj.id), selectedObj?.id].filter(id => id !== undefined), "nodes");
            }
        };

        document.addEventListener('keydown', handleKeyDown);

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [selectedObjects, selectedObj]);

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
        const deleteIdsMap = new Set()

        graph.Elements = {
            nodes: graph.Elements.nodes.filter(node => {
                if (!node.collapsed) return true

                const isTarget = graph.Elements.links.some(link => link.target === node.id && nodes.some(n => n.id === link.source));

                if (!isTarget) return true

                deleteIdsMap.add(node.id)
                const deleted = graph.NodesMap.delete(Number(node.id))

                if (deleted && node.expand) {
                    expandedNodes.push(node)
                }

                return false
            }),
            links: graph.Elements.links
        }

        deleteNeighbors(expandedNodes)?.forEach(id => deleteIdsMap.add(id))

        graph.removeLinks()

        return deleteIdsMap
    }

    const handleExpand = async (nodes: Node[], expand: boolean) => {
        if (expand) {
            const elements = await onFetchNode(nodes.map(n => n.id))

            if (elements.nodes.length === 0) {
                toast({
                    title: `No neighbors found`,
                    description: `No neighbors found`,
                })
                return
            }

            const currentData = canvasRef.current?.getGraphData()

            if (!currentData) return

            // Get existing IDs
            const existingNodeIds = new Set(currentData.nodes.map(n => n.id))
            const existingLinkIds = new Set(currentData.links.map(l => l.id))

            // Filter for only new elements
            const newDataElements = {
                nodes: elements.nodes.filter(n => !existingNodeIds.has(n.id))
                    .map(({ category, color, data, id, isPath, isPathSelected, visible }) => ({
                        color: isPath ? PATH_COLOR : color,
                        id,
                        labels: [category],
                        data: {
                            ...data,
                            isPath,
                            isPathSelected
                        },
                        visible,
                    } as CanvasNode)),
                links: elements.links.filter(l => !existingLinkIds.has(l.id))
                    .map(({ color, id, source, target, data, isPath, isPathSelected, visible, label }) => ({
                        color: isPath ? PATH_COLOR : color,
                        id,
                        source,
                        target,
                        data: {
                            ...data,
                            isPath,
                            isPathSelected
                        },
                        visible,
                        relationship: label,
                    } as CanvasLink))
            }

            // Convert only new data to GraphData format
            const newGraphData = dataToGraphData(
                newDataElements,
                undefined,
                new Map(currentData.nodes.map(n => [n.id, n]))
            )

            // Merge with existing data
            canvasRef.current?.setGraphData({
                nodes: [...currentData.nodes, ...newGraphData.nodes],
                links: [...currentData.links, ...newGraphData.links]
            })

            setCooldownTicks(-1)
        } else {
            const deleteNodes = nodes.filter(n => n.expand)
            if (deleteNodes.length > 0) {
                const deleteIdsMap = deleteNeighbors(deleteNodes);

                if (!deleteIdsMap || deleteIdsMap.size === 0) return

                const currentData = canvasRef.current?.getGraphData()

                if (currentData) {
                    currentData.nodes = currentData.nodes.filter(node => !deleteIdsMap.has(Number(node.id)))
                    currentData.links = currentData.links.filter(link => !deleteIdsMap.has(Number(link.source.id)) && !deleteIdsMap.has(Number(link.target.id)))

                    canvasRef.current?.setGraphData(currentData)
                    setCooldownTicks(-1)
                }
            }
        }

        nodes.forEach((node) => {
            node.expand = expand
        })

        setSelectedObj(undefined)
    }

    const handleRemove = (ids: number[], type: "nodes" | "links") => {
        const canvas = canvasRef.current

        if (!canvas) return

        graph.Elements[type].forEach(element => {
            if (!ids.includes(element.id)) return
            element.visible = false
        })

        const currentData = canvas.getGraphData()

        currentData[type].forEach(element => {
            if (!ids.includes(Number(element.id))) return
            element.visible = false
        })

        if (type === "nodes") {
            currentData.links.forEach((link) => {
                if (ids.includes(link.source.id) || ids.includes(link.target.id)) {
                    link.visible = false
                }
            })
        }

        canvas.setGraphData(currentData)
        graph.visibleLinks(false, ids)
        setHasHiddenElements(true)

        setSelectedObj(undefined)
        setSelectedObjects([])
        setCooldownTicks(-1)
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

                                                    graph.getElements().forEach((element) => {
                                                        element.isPath = false
                                                        element.isPathSelected = false
                                                    })

                                                    const currentData = canvas.getGraphData();

                                                    [...currentData.nodes, ...currentData.links].forEach(element => {
                                                        element.data.isPath = false
                                                        element.data.isPathSelected = false

                                                        if ("source" in element) {
                                                            element.color = "#999999"
                                                        }
                                                    })

                                                    canvas.setGraphData(currentData)
                                                    setIsPathResponse(false)
                                                    setCooldownTicks(-1)
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

                                                    const currentData = canvas.getGraphData();

                                                    [...currentData.nodes, ...currentData.links].forEach(element => {
                                                        element.visible = true
                                                    });

                                                    canvas.setGraphData(currentData);
                                                    setHasHiddenElements(false);
                                                    setCooldownTicks(-1);
                                                }}
                                            >
                                                <X size={15} />
                                                Unhide Nodes
                                            </Button>
                                        }
                                    </div>
                                </div>
                                <ElementMenu
                                    obj={selectedObj}
                                    objects={selectedObjects}
                                    setPath={(path) => {
                                        setPath(path)
                                        setSelectedObj(undefined)
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
                                    selectedObj={selectedObj}
                                    selectedObjects={selectedObjects}
                                    setSelectedObj={setSelectedObj}
                                    setSelectedObjects={setSelectedObjects}
                                    setPosition={setPosition}
                                    handleExpand={handleExpand}
                                    isShowPath={isShowPath}
                                    setPath={setPath}
                                    isPathResponse={isPathResponse}
                                    selectedPathId={selectedPathId}
                                    setSelectedPathId={setSelectedPathId}
                                    cooldownTicks={cooldownTicks}
                                    setCooldownTicks={setCooldownTicks}
                                    setZoomedNodes={setZoomedNodes}
                                    zoomedNodes={zoomedNodes}
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
                                            setCooldownTicks={setCooldownTicks}
                                            cooldownTicks={cooldownTicks}
                                        />
                                    </div>
                                </div>
                            </div>
                            : (
                                isFetchingGraph ?
                                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                        <Loader2 className="md:w-24 md:h-24 w-16 h-16 animate-spin" />
                                        <h1 className="md:text-4xl text-2xl text-center">Fetching graph...</h1>
                                    </div>
                                    :
                                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                        <GitFork className="md:w-24 md:h-24 w-16 h-16" />
                                        <h1 className="md:text-4xl text-2xl text-center">Select a repo to show its graph here</h1>
                                    </div>
                            )
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
