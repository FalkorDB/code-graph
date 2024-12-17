
import ForceGraph2D from 'react-force-graph-2d';
import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, RefObject, SetStateAction, useEffect, useRef } from 'react';
import { toast } from '@/components/ui/use-toast';
import { Path } from '../page';

export interface Position {
    x: number,
    y: number,
}

interface Props {
    data: GraphData
    setData: Dispatch<SetStateAction<GraphData>>
    graph: Graph
    chartRef: RefObject<any>
    selectedObj: Node | undefined
    setSelectedObj: Dispatch<SetStateAction<Node | undefined>>
    selectedObjects: Node[]
    setSelectedObjects: Dispatch<SetStateAction<Node[]>>
    setPosition: Dispatch<SetStateAction<Position | undefined>>
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>
    deleteNeighbors: (nodes: Node[]) => void
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    isPathResponse: boolean | undefined
    selectedPathId: number | undefined
    setSelectedPathId: (selectedPathId: number) => void
    cooldownTicks: number | undefined
    setCooldownTicks: Dispatch<SetStateAction<number | undefined>>
    cooldownTime: number | undefined
    setCooldownTime: Dispatch<SetStateAction<number>>
}

const NODE_SIZE = 6;
const PADDING = 2;

export default function GraphView({
    data,
    setData,
    graph,
    chartRef,
    selectedObj,
    setSelectedObj,
    selectedObjects,
    setSelectedObjects,
    setPosition,
    onFetchNode,
    deleteNeighbors,
    isShowPath,
    setPath,
    isPathResponse,
    selectedPathId,
    setSelectedPathId,
    cooldownTicks,
    cooldownTime,
    setCooldownTicks,
    setCooldownTime
}: Props) {

    const parentRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        setCooldownTime(4000)
        setCooldownTicks(undefined)
    }, [graph.Id])

    useEffect(() => {
        setCooldownTime(1000)
        setCooldownTicks(undefined)
    }, [graph.getElements().length])

    const unsetSelectedObjects = (evt?: MouseEvent) => {
        debugger
        if (evt?.ctrlKey || (!selectedObj && selectedObjects.length === 0)) return
        setSelectedObj(undefined)
        setSelectedObjects([])
    }

    const handelNodeClick = (node: Node, evt: MouseEvent) => {
        if (isShowPath) {
            setPath(prev => {
                if (!prev?.start?.name || (prev.end?.name && prev.end?.name !== "")) {
                    return ({ start: { id: Number(node.id), name: node.name } })
                } else {
                    return ({ end: { id: Number(node.id), name: node.name }, start: prev.start })
                }
            })
            return
        }

        if (evt.ctrlKey) {
            if (selectedObjects.some(obj => obj.id === node.id)) {
                setSelectedObjects(selectedObjects.filter(obj => obj.id !== node.id))
                return
            } else {
                setSelectedObjects([...selectedObjects, node])
            }
        } else {
            setSelectedObjects([])
        }

        setSelectedObj(node)
        setPosition({ x: evt.clientX, y: evt.clientY })
    }

    const handelLinkClick = (link: Link, evt: MouseEvent) => {
        unsetSelectedObjects(evt)
        if (!isPathResponse || link.id === selectedPathId) return
        setSelectedPathId(link.id)
    }

    const handelNodeRightClick = async (node: Node) => {
        const expand = !node.expand
        if (expand) {
            const elements = await onFetchNode([node.id])

            if (elements.nodes.length === 0) {
                toast({
                    title: `No neighbors found`,
                    description: `No neighbors found`,
                })
                return
            }
        } else {
            deleteNeighbors([node]);
        }

        node.expand = expand

        setSelectedObj(undefined)
        setData({ ...graph.Elements })
    }

    return (
        <div ref={parentRef} className="relative w-fill h-full">
            <ForceGraph2D
                ref={chartRef}
                height={parentRef.current?.clientHeight || 0}
                width={parentRef.current?.clientWidth || 0}
                graphData={data}
                nodeVisibility={"visibility"}
                linkVisibility={"visibility"}
                linkLabel={"label"}
                nodeRelSize={NODE_SIZE}
                nodeCanvasObjectMode={() => 'replace'}
                linkCanvasObjectMode={() => 'replace'}
                nodeCanvasObject={(node, ctx) => {
                    if (!node.x || !node.y) return

                    if (isPathResponse) {
                        if (node.isPathSelected) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = '#FF66B3';
                            ctx.lineWidth = 1
                        } else if (node.isPath) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = '#FF66B3';
                            ctx.lineWidth = 0.5
                        } else {
                            ctx.fillStyle = '#E5E5E5';
                            ctx.strokeStyle = 'gray';
                            ctx.lineWidth = 0.5
                        }
                    } else if (isPathResponse === undefined) {
                        if (node.isPathSelected) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = '#FF66B3';
                            ctx.lineWidth = 1
                        } else if (node.isPath) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = '#FF66B3';
                            ctx.lineWidth = 0.5
                        } else {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = 'black';
                            ctx.lineWidth = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id ? 1 : 0.5
                        }
                    } else {
                        ctx.fillStyle = node.color;
                        ctx.strokeStyle = 'black';
                        ctx.lineWidth = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id ? 1 : 0.5
                    }

                    ctx.beginPath();
                    ctx.arc(node.x, node.y, NODE_SIZE, 0, 2 * Math.PI, false);
                    ctx.stroke();
                    ctx.fill();

                    ctx.fillStyle = 'black';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.font = '4px Arial';
                    const textWidth = ctx.measureText(node.name).width;
                    const ellipsis = '...';
                    const ellipsisWidth = ctx.measureText(ellipsis).width;
                    const nodeSize = NODE_SIZE * 2 - PADDING;
                    let { name } = { ...node }

                    // truncate text if it's too long
                    if (textWidth > nodeSize) {
                        while (name.length > 0 && ctx.measureText(name).width + ellipsisWidth > nodeSize) {
                            name = name.slice(0, -1);
                        }
                        name += ellipsis;
                    }

                    // add label
                    ctx.fillText(name, node.x, node.y);
                }}
                linkCanvasObject={(link, ctx) => {
                    if (!link.source.x || !link.source.y || !link.target.x || !link.target.y) return

                    //give path links a different color
                    if (isPathResponse || isPathResponse === undefined) {
                        if (link.isPathSelected) {
                            ctx.strokeStyle = '#FF66B3';
                            ctx.lineWidth = 1
                            ctx.setLineDash([]);
                        } else if (link.isPath) {
                            ctx.strokeStyle = '#FF66B3';
                            ctx.lineWidth = 0.5
                            ctx.setLineDash([5, 5]);
                        } else {
                            ctx.strokeStyle = 'gray';
                            ctx.lineWidth = 0.5
                            ctx.setLineDash([]);
                        }
                    } else {
                        ctx.strokeStyle = 'gray';
                        ctx.lineWidth = 0.5
                        ctx.setLineDash([]);
                    }

                    ctx.beginPath();

                    if (link.source.id === link.target.id) {
                        // handel self closing link
                        ctx.lineWidth = ctx.lineWidth * 2
                        ctx.moveTo(link.source.x, link.source.y);
                        ctx.arcTo(link.target.x + 20, link.target.y + 35, link.target.x - 20, link.target.y + 20, 10);
                        ctx.arcTo(link.target.x - 20, link.target.y + 20, link.target.x, link.target.y, 10);
                        ctx.closePath();
                    } else {
                        // handel multiple links between same nodes
                        const sameNodeLinks = data.links.filter(l =>
                            ((l.source.id === link.source.id && l.target.id === link.target.id) ||
                                (l.source.id === link.target.id && l.target.id === link.source.id))
                            && l.id !== link.id
                        );

                        const linkIndex = sameNodeLinks.findIndex(l => l.id === link.id);
                        const offset = linkIndex === -1 ? 0 : (linkIndex) * 5;

                        // add link
                        ctx.moveTo(link.source.x, link.source.y);
                        ctx.lineTo(link.target.x + offset, link.target.y + offset);
                    }
                    ctx.stroke();

                    // add label box
                    const midX = (link.source.x + link.target.x) / 2;
                    const midY = (link.source.y + link.target.y) / 2;
                    ctx.fillStyle = 'white';
                    ctx.fill();
                    const labelWidth = ctx.measureText(link.label).width
                    ctx.fillRect(midX - (labelWidth + 1) / 2, midY - 2.184, labelWidth + 1, 3.833);

                    // add label
                    ctx.fillStyle = 'black';
                    ctx.font = '4px Arial';
                    ctx.fillText(link.label, midX, midY);
                }}
                onNodeClick={handelNodeClick}
                onNodeDragEnd={(n, translate) => setPosition(prev => {
                    return prev && { x: prev.x + translate.x * chartRef.current.zoom(), y: prev.y + translate.y * chartRef.current.zoom() }
                })}
                onNodeRightClick={handelNodeRightClick}
                onLinkClick={handelLinkClick}
                onBackgroundRightClick={unsetSelectedObjects}
                onBackgroundClick={unsetSelectedObjects}
                onZoom={() => unsetSelectedObjects()}
                onEngineStop={() => {
                    setCooldownTicks(0)
                    setCooldownTime(0)
                }}
                cooldownTicks={cooldownTicks}
                cooldownTime={cooldownTime}
            />
        </div>
    )
}