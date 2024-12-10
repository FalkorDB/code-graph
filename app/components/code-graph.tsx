import { Dispatch, RefObject, SetStateAction, useContext, useEffect, useRef, useState } from "react";
import { GraphData, Node } from "./model";
import { GraphContext } from "./provider";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { GitFork, Search, X } from "lucide-react";
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

const GraphView = dynamic(() => import('./graphView'));

interface Props {
    data: GraphData,
    setData: Dispatch<SetStateAction<GraphData>>,
    onFetchGraph: (graphName: string) => void,
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>,
    options: string[]
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
    const [position, setPosition] = useState<Position>();
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
        if (containerRef.current) {
            setContainerWidth(containerRef.current.clientWidth);
        }
    }, [containerRef.current]);

    useEffect(() => {
        setData({ ...graph.Elements })
    }, [graph])

    useEffect(() => {
        if (!selectedValue) return
        handleSelectedValue(selectedValue)
    }, [selectedValue])

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Delete') {
                if (selectedObj && selectedObjects.length === 0) return
                handelRemove([...selectedObjects.map(obj => obj.id), selectedObj?.id].filter(id => id !== undefined));
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

    function handleSelectedValue(value: string) {
        setGraphName(value)
        onFetchGraph(value)
    }

    function onCategoryClick(name: string, show: boolean) {
        const elements: Node[] = []

        graph.Categories.find(c => c.name === name)!.show = show

        graph.Elements.nodes.forEach(node => {
            if (node.category === name) {
                node.visibility = show
                elements.push(node)
            }
        })

        graph.visibleLinks()

        setData({ ...graph.Elements })
    }

    const deleteNeighbors = (nodes: Node[]) => {
        if (nodes.length === 0) return;

        graph.Elements = {
            nodes: graph.Elements.nodes.map(node => {
                const isTarget = graph.Elements.links.some(link => link.target.id === node.id && nodes.some(n => n.id === link.source.id));

                if (!isTarget || !node.collapsed) return node

                if (node.expand) {
                    node.expand = false
                    deleteNeighbors([node])
                }

                graph.NodesMap.delete(Number(node.id))
            }).filter(node => node !== undefined),
            links: graph.Elements.links
        }

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

            graph.Elements = {
                nodes: [...graph.Elements.nodes, ...elements.nodes],
                links: [...graph.Elements.links, ...elements.links]
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

    const handelSearchSubmit = (node: any) => {
        const n = { name: node.properties.name, id: node.id }

        let chartNode = graph.Elements.nodes.find(n => n.id == node.id)

        if (!chartNode?.visible) {
            if (!chartNode) {
                chartNode = graph.extend({ nodes: [node], edges: [] }).nodes[0]
            } else {
                chartNode.visibility = true
            }
            graph.visibleLinks([chartNode.id], true)
        }

        setSearchNode(n)
        setData({ ...graph.Elements })

        const chart = chartRef.current

        if (chart) {
            chart.centerAt(chartNode.x, chartNode.y, 1000);
        }
    }

    const handelRemove = (ids: number[]) => {
        graph.Elements = {
            nodes: graph.Elements.nodes.map(node => ids.includes(node.id) ? { ...node, visibility: false } : node),
            links: graph.Elements.links
        }

        graph.visibleLinks(ids, false)

        setData({ ...graph.Elements })
    }

    return (
        <div className="h-full w-full flex flex-col gap-4 p-8 bg-gray-100">
            <header className="flex flex-col gap-4">
                <Combobox
                    options={options}
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
                                            value={searchNode.name}
                                            onValueChange={({ name }) => setSearchNode({ name })}
                                            icon={<Search />}
                                            handleSubmit={handelSearchSubmit}
                                            node={searchNode}
                                        />
                                        <Labels categories={graph.Categories} onClick={onCategoryClick} />
                                    </div>
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
                                        />
                                    </div>
                                </div>
                                <ElementMenu
                                    obj={selectedObj}
                                    objects={selectedObjects}
                                    setPath={(path) => {
                                        setPath(path)
                                        setSelectedObj(undefined)
                                    }}
                                    handleRemove={handelRemove}
                                    position={position}
                                    url={url}
                                    handelExpand={handleExpand}
                                    parentRef={containerRef}
                                />
                                <GraphView
                                    data={data}
                                    setData={setData}
                                    graph={graph}
                                    chartRef={chartRef}
                                    selectedObj={selectedObj}
                                    setSelectedObj={setSelectedObj}
                                    setPosition={setPosition}
                                    onFetchNode={onFetchNode}
                                    deleteNeighbors={deleteNeighbors}
                                    parentRef={containerRef}
                                    isShowPath={isShowPath}
                                    setPath={setPath}
                                    isPathResponse={isPathResponse}
                                    selectedPathId={selectedPathId}
                                    setSelectedPathId={setSelectedPathId}
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
