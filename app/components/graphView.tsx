
import ForceGraph2D from 'react-force-graph-2d';
import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, Ref, RefObject, SetStateAction, useCallback } from 'react';
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
    setPosition: Dispatch<SetStateAction<Position | undefined>>
    onFetchNode: (nodeIds: string[]) => Promise<GraphData>
    deleteNeighbors: (nodes: Node[]) => void
    parentRef: RefObject<HTMLDivElement>
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    isPathResponse: boolean | undefined
    selectedPathId: string | undefined
    setSelectedPathId: (selectedPathId: string) => void
}

const NODE_SIZE = 6;

export default function GraphView({
    data,
    setData,
    graph,
    chartRef,
    selectedObj,
    setSelectedObj,
    setPosition,
    onFetchNode,
    deleteNeighbors,
    parentRef,
    isShowPath,
    setPath,
    isPathResponse,
    selectedPathId,
    setSelectedPathId
}: Props) {
    const unsetSelectedObj = () => {
        setSelectedObj(undefined)
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
        setSelectedObj(node)
        setPosition({ x: evt.clientX, y: evt.clientY })
    }

    const handelLinkClick = (link: Link) => {
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

            graph.Elements = {
                nodes: [...graph.Elements.nodes, ...elements.nodes],
                links: [...graph.Elements.links, ...elements.links]
            }
        } else {
            deleteNeighbors([node]);
        }

        node.expand = expand

        setSelectedObj(undefined)
        setData({ ...graph.Elements })
    }

    return (
        <div className="relative w-fill h-full">
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
                            ctx.strokeStyle = 'black';
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
                            ctx.lineWidth = selectedObj?.id === node.id ? 1 : 0.5
                        }
                    } else {
                        ctx.fillStyle = node.color;
                        ctx.strokeStyle = 'black';
                        ctx.lineWidth = selectedObj?.id === node.id ? 1 : 0.5
                    }

                    ctx.beginPath();
                    ctx.arc(node.x, node.y, NODE_SIZE, 0, 2 * Math.PI, false);
                    ctx.stroke();
                    ctx.fill();
                }}
                linkCanvasObject={(link, ctx) => {
                    if (!link.source.x || !link.source.y || !link.target.x || !link.target.y) return

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
                    ctx.moveTo(link.source.x, link.source.y);
                    ctx.lineTo(link.target.x, link.target.y);
                    ctx.stroke();
                    ctx.fill();
                }}
                onNodeClick={handelNodeClick}
                onNodeDrag={unsetSelectedObj}
                onNodeRightClick={handelNodeRightClick}
                onLinkClick={handelLinkClick}
                onBackgroundRightClick={unsetSelectedObj}
                onBackgroundClick={unsetSelectedObj}
                onZoom={unsetSelectedObj}
            />
        </div>
    )
}