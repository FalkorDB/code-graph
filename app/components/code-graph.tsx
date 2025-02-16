import { Dispatch, RefObject, SetStateAction, useContext, useEffect, useRef, useState } from "react";
import { GraphData, Link, Node } from "./model";
import { GraphContext } from "./provider";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { Download, GitFork, Search, X } from "lucide-react";
import ElementMenu from "./elementMenu";
import Combobox from "./combobox";
import { toast } from '@/components/ui/use-toast';
import { Path, PathNode } from '../page';
import Input from './Input';
// import CommitList from './commitList';
import { Checkbox } from '@/components/ui/checkbox';
import dynamic from 'next/dynamic';
import { Position } from "./graphView";
import { prepareArg } from '../utils';
import { NodeObject } from "react-force-graph-2d";
import { Switch } from "@/components/ui/switch"

const GraphView = dynamic(() => import('./graphView'));

interface Props {
    data: GraphData,
    setData: Dispatch<SetStateAction<GraphData>>,
    onFetchGraph: (graphName: string) => Promise<void>,
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>,
    options: string[]
    setOptions: Dispatch<SetStateAction<string[]>>
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    chartRef: RefObject<any>
    selectedValue: string
    selectedPathId: number | undefined
    setSelectedPathId: (selectedPathId: number) => void
    isPathResponse: boolean | undefined
    setIsPathResponse: Dispatch<SetStateAction<boolean | undefined>>
}

export function CodeGraph({
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
    selectedPathId
}: Props) {

    let graph = useContext(GraphContext)

    const [url, setURL] = useState("");
    const [selectedObj, setSelectedObj] = useState<Node | Link>();
    const [selectedObjects, setSelectedObjects] = useState<Node[]>([]);
    const [position, setPosition] = useState<Position>();
    const [graphName, setGraphName] = useState<string>("");
    const [searchNode, setSearchNode] = useState<PathNode>({});
    const [commits, setCommits] = useState<any[]>([]);
    const [nodesCount, setNodesCount] = useState<number>(0);
    const [edgesCount, setEdgesCount] = useState<number>(0);
    const [commitIndex, setCommitIndex] = useState<number>(0);
    const [currentCommit, setCurrentCommit] = useState(0);
    const [cooldownTicks, setCooldownTicks] = useState<number | undefined>(0)
    const [cooldownTime, setCooldownTime] = useState<number>(0)
    const containerRef = useRef<HTMLDivElement>(null);
    const [isTreeLayout, setIsTreeLayout] = useState(false);

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
                handleRemove([...selectedObjects.map(obj => obj.id), selectedObj?.id].filter(id => id !== undefined));
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

    function onCategoryClick(name: string, show: boolean) {
        graph.Categories.find(c => c.name === name)!.show = show

        graph.Elements.nodes.forEach(node => {
            if (!(node.category === name)) return
            node.visible = show
        })

        graph.visibleLinks(show)

        setData({ ...graph.Elements })
    }

    const deleteNeighbors = (nodes: Node[]) => {
        
        if (nodes.length === 0) return;
        
        const expandedNodes: Node[] = []
        
        graph.Elements = {
            nodes: graph.Elements.nodes.filter(node => {
                if (!node.collapsed) return true
                
                const isTarget = graph.Elements.links.some(link => link.target.id === node.id && nodes.some(n => n.id === link.source.id));
                
                debugger

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

    const handleSearchSubmit = (node: any) => {
        const chart = chartRef.current

        if (chart) {

            let chartNode = graph.Elements.nodes.find(n => n.id == node.id)

            if (!chartNode?.visible) {
                if (!chartNode) {
                    chartNode = graph.extend({ nodes: [node], edges: [] }).nodes[0]
                } else {
                    chartNode.visible = true
                    setCooldownTicks(undefined)
                    setCooldownTime(1000)
                }
                graph.visibleLinks(true, [chartNode!.id])
                setData({ ...graph.Elements })
            }
          
            setSearchNode(chartNode)
            setTimeout(() => {
                chart.zoomToFit(1000, 150, (n: NodeObject<Node>) => n.id === chartNode!.id);
            }, 0)
        }
    }

    const handleRemove = (ids: number[]) => {
        graph.Elements.nodes.forEach(node => {
            if (!ids.includes(node.id)) return
            node.visible = false
        })

        graph.visibleLinks(false, ids)

        setData({ ...graph.Elements })
    }

    const handleDownloadImage = async () => {
        try {
            const canvas = document.querySelector('.force-graph-container canvas') as HTMLCanvasElement;
            if (!canvas) {
                toast({
                    title: "Error",
                    description: "Canvas not found",
                    variant: "destructive",
                });
                return;
            }

            const dataURL = canvas.toDataURL('image/webp');
            const link = document.createElement('a');
            link.href = dataURL;
            link.download = `${graphName}.webp`;
            link.click();
        } catch (error) {
            console.error('Error downloading graph image:', error);
            toast({
                title: "Error",
                description: "Failed to download image. Please try again.",
                variant: "destructive",
            });
        }
    };

    return (
        <div className="h-full w-full flex flex-col gap-4 p-8 bg-gray-100">
            <header className="flex flex-col gap-4">
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
                            <div className="h-full relative border">
                                <div className="w-full absolute top-0 left-0 flex justify-between p-4 z-10 pointer-events-none">
                                    <div className='flex gap-4'>
                                        <Input
                                            graph={graph}
                                            onValueChange={(node) => setSearchNode(node)}
                                            icon={<Search />}
                                            handleSubmit={handleSearchSubmit}
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
                                            (graph.Elements.nodes.some(e => !e.visible)) &&
                                            <button
                                                className='bg-[#ECECEC] hover:bg-[#D3D3D3] p-2 rounded-md flex gap-2 items-center pointer-events-auto'
                                                onClick={() => {
                                                    graph.Categories.forEach(c => c.show = true)
                                                    graph.Elements.nodes.forEach((element) => {
                                                        element.visible = true
                                                    })
                                                    graph.visibleLinks(true)

                                                    setData({ ...graph.Elements })
                                                }}
                                            >
                                                <X size={15} />
                                                <p>Unhide Nodes</p>
                                            </button>
                                        }
                                    </div>
                                </div>
                                <div data-name="canvas-info-panel" className="w-full absolute bottom-0 left-0 flex justify-between items-center p-4 z-10 pointer-events-none">
                                    <div data-name="metrics-panel" className="flex gap-4 text-gray-500">
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
                                        <div className="flex items-center gap-2 pointer-events-auto">
                                            <p className="text-sm text-gray-500">Tree Layout</p>
                                            <Switch
                                                checked={isTreeLayout}
                                                onCheckedChange={setIsTreeLayout}
                                            />
                                        </div>
                                        <Toolbar
                                            className="pointer-events-auto"
                                            chartRef={chartRef}
                                        />
                                        <button
                                            className="pointer-events-auto bg-white p-2 rounded-md"
                                            onClick={handleDownloadImage}
                                        >
                                            <Download />
                                        </button>
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
                                    onFetchNode={onFetchNode}
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
                                    isTreeLayout={isTreeLayout}
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
