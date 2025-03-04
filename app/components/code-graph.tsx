import { Dispatch, SetStateAction, useEffect, useRef, useState } from "react";
import { Graph, GraphData, Node, Link } from "./model";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { GitFork, Search, X } from "lucide-react";
import ElementMenu from "./elementMenu";
import Combobox from "./combobox";
import { toast } from '@/components/ui/use-toast';
import { handleZoomToFit, Path } from "@/lib/utils";
import Input from './Input';
// import CommitList from './commitList';
import { Checkbox } from '@/components/ui/checkbox';
import dynamic from 'next/dynamic';
import { Position } from "./graphView";
import { prepareArg } from '../utils';
import { GraphRef } from "@/lib/utils";
import { NodeObject } from "react-force-graph-2d";

const GraphView = dynamic(() => import('./graphView'));

interface Props {
    graph: Graph,
    data: GraphData,
    setData: Dispatch<SetStateAction<GraphData>>,
    onFetchGraph: (graphName: string) => Promise<void>,
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>,
    options: string[]
    setOptions: Dispatch<SetStateAction<string[]>>
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    chartRef: GraphRef
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
    cooldownTime: number
    setCooldownTime: Dispatch<SetStateAction<number>>
    onCategoryClick: (name: string, show: boolean) => void
    handleDownloadImage: () => void
}

export function CodeGraph({
    graph,
    data,
    setData,
    onFetchGraph,
    onFetchNode,
    options,
    setOptions,
    isShowPath,
    setPath,
    chartRef,
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
    cooldownTime,
    setCooldownTime,
    onCategoryClick,
    handleDownloadImage
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

    useEffect(() => {
        setData({ ...graph.Elements })
    }, [graph.Id])

    useEffect(() => {
        if (!selectedValue) return
        handleSelectedValue(selectedValue)
    }, [selectedValue])

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Delete') {
                if (selectedObj && selectedObjects.length === 0) return
                handleRemove([...selectedObjects.map(obj => obj.id), selectedObj?.id].filter(id => id !== undefined), "nodes");
            }
        };

        document.addEventListener('keydown', handleKeyDown);

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [selectedObjects, selectedObj]);

    async function fetchCount() {
        const result = await fetch(`/api/repo/${prepareArg(graphName)}/info`, {
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

    async function handleSelectedValue(value: string) {
        setGraphName(value)
        onFetchGraph(value)
    }

    const deleteNeighbors = (nodes: Node[]) => {

        if (nodes.length === 0) return;

        const expandedNodes: Node[] = []

        graph.Elements = {
            nodes: graph.Elements.nodes.filter(node => {
                if (!node.collapsed) return true

                const isTarget = graph.Elements.links.some(link => link.target.id === node.id && nodes.some(n => n.id === link.source.id));

                if (!isTarget) return true

                const deleted = graph.NodesMap.delete(Number(node.id))

                if (deleted && node.expand) {
                    expandedNodes.push(node)
                }

                return false
            }),
            links: graph.Elements.links
        }

        deleteNeighbors(expandedNodes)

        graph.removeLinks()
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
        } else {
            const deleteNodes = nodes.filter(n => n.expand)
            if (deleteNodes.length > 0) {
                deleteNeighbors(deleteNodes);
            }
        }

        nodes.forEach((node) => {
            node.expand = expand
        })

        setSelectedObj(undefined)
        setData({ ...graph.Elements })
    }

    const handleRemove = (ids: number[], type: "nodes" | "links") => {
        graph.Elements[type].forEach(element => {
            if (!ids.includes(element.id)) return
            element.visible = false
        })

        graph.visibleLinks(false, ids)

        setSelectedObj(undefined)
        setSelectedObjects([])

        setData({ ...graph.Elements })
    }

    return (
        <div className="grow md:h-full w-full flex flex-col gap-4 p-4 pt-0 md:p-8 md:bg-gray-100">
            <header className="flex flex-col gap-4 relative">
                <div className="absolute md:hidden inset-x-0 top-8 h-[50%] bg-gray-100 -mx-8 -mt-8 px-8 border-b border-gray-400" />
                <Combobox
                    options={options}
                    setOptions={setOptions}
                    selectedValue={graphName}
                    onSelectedValue={handleSelectedValue}
                />
            </header>
            <div className='h-1 grow flex flex-col'>
                <main ref={containerRef} className="bg-white h-1 grow">
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
                                                setTimeout(() => {
                                                    handleZoomToFit(chartRef, (n: NodeObject<Node>) => n.id === node.id);
                                                }, 1000);
                                            }}
                                            node={searchNode}
                                        />
                                        <Labels categories={graph.Categories} onClick={onCategoryClick} />
                                    </div>
                                    <div className="flex gap-2">
                                        {
                                            (isPathResponse || isPathResponse === undefined) &&
                                            <button
                                                className='bg-[#ECECEC] hover:bg-[#D3D3D3] p-2 rounded-md flex gap-2 items-center pointer-events-auto'
                                                onClick={() => {
                                                    graph.getElements().forEach((element) => {
                                                        element.isPath = false
                                                        element.isPathSelected = false
                                                    })
                                                    setIsPathResponse(false)
                                                }}
                                            >
                                                <X size={15} />
                                                <p>Reset Graph</p>
                                            </button>
                                        }
                                        {
                                            (graph.getElements().some(e => !e.visible)) &&
                                            <button
                                                className='bg-[#ECECEC] hover:bg-[#D3D3D3] p-2 rounded-md flex gap-2 items-center pointer-events-auto'
                                                onClick={() => {
                                                    graph.Categories.forEach(c => c.show = true)
                                                    graph.getElements().forEach((element) => {
                                                        element.visible = true
                                                    })

                                                    setData({ ...graph.Elements })
                                                }}
                                            >
                                                <X size={15} />
                                                <p>Unhide Nodes</p>
                                            </button>
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
                                    data={data}
                                    setData={setData}
                                    graph={graph}
                                    chartRef={chartRef}
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
                                    cooldownTime={cooldownTime}
                                    setCooldownTime={setCooldownTime}
                                />
                                <div data-name="canvas-info-panel" className="w-full md:absolute md:bottom-0 md:left-0 md:flex md:justify-between md:items-center md:p-4 z-10 pointer-events-none">
                                    <div data-name="metrics-panel" className="flex gap-4 justify-center bg-gray-100 md:bg-transparent md:text-gray-500 p-2 md:p-0">
                                        <p>{nodesCount} Nodes</p>
                                        <p className="md:hidden">|</p>
                                        <p>{edgesCount} Edges</p>
                                    </div>
                                    <div className='hidden md:flex gap-4'>
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
                                            className="gap-4"
                                            chartRef={chartRef}
                                            handleDownloadImage={handleDownloadImage}
                                        />
                                    </div>
                                </div>
                            </div>
                            : <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                <GitFork className="md:w-24 md:h-24 w-16 h-16" color="gray" />
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
