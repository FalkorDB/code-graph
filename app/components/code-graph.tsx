import { Dispatch, SetStateAction, useContext, useEffect, useRef, useState } from "react";
import { Edge, GraphData, Node } from "./model";
import { GraphContext } from "./provider";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { GitFork, Search, X } from "lucide-react";
import ElementMenu from "./elementMenu";
import Combobox from "./combobox";
import { toast } from '@/components/ui/use-toast';
import { Path } from '../page';
import Input from './Input';
import CommitList, { CommitChanges } from './commitList';
import { Checkbox } from '@/components/ui/checkbox';
import GraphView from "./graphView";

interface Props {
    onFetchGraph: (graphName: string) => void,
    onFetchNode: (node: Node) => Promise<GraphData>,
    options: string[]
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    selectedValue: string
    setSelectedPathId: (selectedPathId: string) => void
    isPathResponse: boolean
    setIsPathResponse: Dispatch<SetStateAction<boolean>>
}

export function CodeGraph({
    onFetchGraph,
    onFetchNode,
    options,
    isShowPath,
    setPath,
    selectedValue,
    setSelectedPathId,
    isPathResponse,
    setIsPathResponse
}: Props) {

    let graph = useContext(GraphContext)

    const [url, setURL] = useState("");
    const [data, setData] = useState<GraphData>(graph.Elements);
    const [selectedObj, setSelectedObj] = useState<Node>();
    const [position, setPosition] = useState<{ x: number, y: number }>();
    const [graphName, setGraphName] = useState<string>("");
    const [searchNodeName, setSearchNodeName] = useState<string>("");
    const [commits, setCommits] = useState<any[]>([]);
    const [nodesCount, setNodesCount] = useState<number>(0);
    const [edgesCount, setEdgesCount] = useState<number>(0);
    const [commitIndex, setCommitIndex] = useState<number>(0);
    const [currentCommit, setCurrentCommit] = useState(0);
    const [commitChanges, setCommitChanges] = useState<CommitChanges>();
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<any>();

    useEffect(() => {
        setData({ ...graph.Elements })
    }, [graph])

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
        let elements = graph.Elements.nodes.filter(e => e.category === name)

        graph.Categories.forEach((category) => {
            if (category.name === name) {
                category.show = show
            }
        })

        if (show) {
            elements.forEach((element) => {
                element.nodeVisibility = true
            })
        } else {
            elements.forEach((element) => {
                element.nodeVisibility = false
            })
        }

        graph.Elements.links.forEach((link) => {
            if (show) {
                    if (elements.some(e => e.id === String((link.source as unknown as Edge).id) || e.id === String((link.target as unknown as Edge).id)) && graph.Elements.nodes.some(e => e.id === (String((link.source as unknown as Edge).id) && (link.source as unknown as Edge).linkVisible) || (e.id === String((link.target as unknown as Edge).id) && (link.target as unknown as Edge).linkVisible))) {
                        link.linkVisibility = true
                    }
                } else {
                    if (elements.some(e => e.id === String((link.source as unknown as Edge).id) || e.id === String((link.target as unknown as Edge).id))) {
                        link.linkVisibility = false
                    }
                }
        })
        
        setData({ ...graph.Elements })
        chartRef.current?.zoomToFit(1000, 200);
    }

    const deleteNeighbors = (node: Node) => {
        const { id } = node
        const neighbors = graph.Elements.nodes.filter(n => graph.Elements.links.filter(e => String((e.source as unknown as Edge).id) === id).some(e => String((e.target as unknown as Edge).id) === n.id))

        neighbors.forEach((n) => {
            if (!n || !n.collapsed) return

            if (n.expand) {
                deleteNeighbors(n)
            }

            graph.Elements = {
                nodes: graph.Elements.nodes.filter(e => e.id !== n.id),
                links: graph.Elements.links.filter(e => {
                    if (String((e.target as unknown as Edge).id) === n.id || String((e.source as unknown as Edge).id) === n.id) {
                        graph.EdgesMap.delete(Number(e.id))
                        return false
                    }
                    return true
                })
            }

            graph.NodesMap.delete(Number(n.id))
        })
    }
    
    const handleNodeRightTap = async (node?: Node) => {

        node ??= selectedObj

        if (!node) return
        
        if (!node.expand) {
            const elements = await onFetchNode(node)
            if (elements.nodes.length === 0) {
                toast({
                    title: "No neighbors found",
                })
                return
            }
        } else {
            deleteNeighbors(node)
        }
        
        node.expand = !node.expand;
        setSelectedObj(undefined)
        setData({ ...graph.Elements })
        chartRef.current?.zoomToFit(1000, 200);
    }

    const handelSearchSubmit = (node: any) => {
        let graphNode = graph.Elements.nodes.find(e => e.name === node.name)

        if (!graphNode) {
            [graphNode] = graph.extend({ nodes: [node], edges: [] }).nodes
            setData({ ...graph.Elements })
        }

        setSearchNodeName("")
        chartRef.current?.zoomToFit(1000, 200);
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

                <main className="bg-white h-1 grow">
                    {
                        graph.Id ?
                            <div ref={containerRef} className="h-full relative border">
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
                                            commitChanges &&
                                            <div className='bg-white flex gap-2 border rounded-md p-2 pointer-events-auto'>
                                                <div className='flex gap-2 items-center'>
                                                    <Checkbox
                                                        className='h-5 w-5 bg-gray-500 data-[state=checked]:bg-gray-500'
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
                                        <Toolbar className="pointer-events-auto" chartRef={chartRef} />
                                    </div>
                                </div>
                                <ElementMenu
                                    obj={selectedObj}
                                    position={position}
                                    url={url}
                                    handelMaximize={handleNodeRightTap}
                                />
                                <GraphView
                                    height={containerRef.current?.clientHeight || 0}
                                    width={containerRef.current?.clientWidth || 0}
                                    chartRef={chartRef}
                                    data={data}
                                    isShowPath={isShowPath}
                                    isPathResponse={isPathResponse}
                                    setPath={setPath}
                                    setPosition={setPosition}
                                    setSelectedObj={setSelectedObj}
                                    setSelectedPathId={setSelectedPathId}
                                    handelNodeRightTap={handleNodeRightTap}
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
                        commitChanges={commitChanges}
                        setCommitChanges={setCommitChanges}
                        commitIndex={commitIndex}
                        commits={commits}
                        currentCommit={currentCommit}
                        setCommitIndex={setCommitIndex}
                        setCurrentCommit={setCurrentCommit}
                        graph={graph}
                    />
                }
            </div>
        </div>
    )
}