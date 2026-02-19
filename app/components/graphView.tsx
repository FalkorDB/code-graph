'use client'

import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react';
import { Path, PATH_COLOR } from '@/lib/utils';
import { Fullscreen } from 'lucide-react';
import { GraphRef } from '@/lib/utils';
import ForceGraph from './ForceGraph';
import { GraphLink, GraphNode } from '@falkordb/canvas';

export interface Position {
    x: number,
    y: number,
}

interface Props {
    data: GraphData
    setData: Dispatch<SetStateAction<GraphData>>
    graph: Graph
    chartRef: GraphRef
    selectedObj: Node | Link | undefined
    setSelectedObj: Dispatch<SetStateAction<Node | Link | undefined>>
    selectedObjects: Node[]
    setSelectedObjects: Dispatch<SetStateAction<Node[]>>
    setPosition: Dispatch<SetStateAction<Position | undefined>>
    handleExpand: (nodes: Node[],  expand: boolean) => void
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    isPathResponse: boolean | undefined
    selectedPathId: number | undefined
    setSelectedPathId: (selectedPathId: number) => void
    cooldownTicks: number | undefined
    setCooldownTicks: Dispatch<SetStateAction<number | undefined>>
    setZoomedNodes: Dispatch<SetStateAction<Node[]>>
    zoomedNodes: Node[]
}

const NODE_SIZE = 6;
const PADDING = 2;

export default function GraphView({
    data,
    graph,
    chartRef: canvasRef,
    selectedObj,
    setSelectedObj,
    selectedObjects,
    setSelectedObjects,
    setPosition,
    handleExpand,
    isShowPath,
    setPath,
    isPathResponse,
    selectedPathId,
    setSelectedPathId,
    cooldownTicks,
    setCooldownTicks,
    zoomedNodes,
    setZoomedNodes
}: Props) {

    const lastClick = useRef<{ date: Date, name: string }>({ date: new Date(), name: "" })
    const [screenSize, setScreenSize] = useState<number>(0)

    useEffect(() => {
        const handleResize = () => {
            setScreenSize(window.innerWidth)
        }

        handleResize()

        window.addEventListener('resize', handleResize)

        return () => {
            window.removeEventListener('resize', handleResize)
        }
    }, [])

    const unsetSelectedObjects = useCallback((evt?: MouseEvent) => {
        if (evt?.ctrlKey || (!selectedObj && selectedObjects.length === 0)) return
        setSelectedObj(undefined)
        setSelectedObjects([])
    }, [selectedObj, selectedObjects, setSelectedObj, setSelectedObjects])

    const handleRightClick = useCallback((element: Node | Link, evt: MouseEvent) => {
        if (evt.ctrlKey && "category" in element) {
            if (selectedObjects.some(obj => obj.id === element.id)) {
                setSelectedObjects(selectedObjects.filter(obj => obj.id !== element.id))
                return
            } else {
                setSelectedObjects([...selectedObjects, element as Node])
            }
        } else {
            setSelectedObjects([])
        }

        setSelectedObj(element)
        setPosition({ x: evt.clientX, y: evt.clientY })
    }, [selectedObjects, setSelectedObjects, setSelectedObj, setPosition])

    const handleLinkClick = (link: Link, evt: MouseEvent) => {
        unsetSelectedObjects(evt)
        if (!isPathResponse || link.id === selectedPathId) return
        setSelectedPathId(link.id)
    }

    const handleNodeClick = useCallback(async (node: Node) => {
        const now = new Date()
        const { date, name } = lastClick.current

        const isDoubleClick = now.getTime() - date.getTime() < 1000 && name === node.data.name
        lastClick.current = { date: now, name: node.data.name }

        if (isDoubleClick) {
            handleExpand([node], !node.expand)
        } else if (isShowPath) {
            setPath(prev => {
                if (!prev?.start?.name || (prev.end?.name && prev.end?.name !== "")) {
                    return ({ start: { id: Number(node.id), name: node.data.name } })
                } else {
                    return ({ end: { id: Number(node.id), name: node.data.name }, start: prev.start })
                }
            })
            return
        }
    }, [handleExpand, isShowPath, setPath])

    const handleEngineStop = useCallback(() => {
        if (zoomedNodes.length > 0) {
            canvasRef.current?.zoomToFit(zoomedNodes.length === 1 ? 4 : 1, (n: GraphNode) => zoomedNodes.some(node => node.id === n.id))
            setZoomedNodes([])
        }

        if (cooldownTicks !== -1) return

        setCooldownTicks(0)
    }, [zoomedNodes, cooldownTicks, canvasRef])

    const nodeCanvasObject = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D) => {
        if (!node.x || !node.y) return

        if (isPathResponse) {
            if (node.data.isPathSelected) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = 1.5
            } else if (node.data.isPath) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = 1
            } else {
                ctx.fillStyle = '#E5E5E5';
                ctx.strokeStyle = 'gray';
                ctx.lineWidth = 1
            }
        } else if (isPathResponse === undefined) {
            if (node.data.isPathSelected) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = 1.5
            } else if (node.data.isPath) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = 1
            } else {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = 'black';
                ctx.lineWidth = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id ? 1.5 : 1
            }
        } else {
            ctx.fillStyle = node.color;
            ctx.strokeStyle = 'black';
            ctx.lineWidth = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id ? 1.5 : 1
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_SIZE + ctx.lineWidth / 2, 0, 2 * Math.PI, false);
        ctx.stroke();
        ctx.fill();

        ctx.fillStyle = 'black';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '4px Arial';
        let name = node.data.name || "";
        const textWidth = ctx.measureText(name).width;
        const ellipsis = '...';
        const ellipsisWidth = ctx.measureText(ellipsis).width;
        const nodeSize = (NODE_SIZE + ctx.lineWidth / 2) * 2 - PADDING;

        // truncate text if it's too long
        if (textWidth > nodeSize) {
            while (name.length > 0 && ctx.measureText(name).width + ellipsisWidth > nodeSize) {
                name = name.slice(0, -1);
            }
            name += ellipsis;
        }

        // add label
        ctx.fillText(name, node.x, node.y);
    }, [selectedObj, selectedObjects, isPathResponse])

    const nodePointerAreaPaint = useCallback((node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
        if (!node.x || !node.y) return

        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_SIZE + 4 + ctx.lineWidth / 2, 0, 2 * Math.PI, false);
        ctx.fill();
    }, [])

    const linkCanvasObject = useCallback((link: GraphLink, ctx: CanvasRenderingContext2D) => {
        const start = link.source;
        const end = link.target;

        if (!start.x || !start.y || !end.x || !end.y) return

        const sameNodesLinks = graph.Elements.links.filter(l => (l.source === start.id && l.target === end.id) || (l.target === start.id && l.source === end.id))
        const index = sameNodesLinks.findIndex(l => l.id === link.id) || 0
        const even = index % 2 === 0
        let curve

        if (start.id === end.id) {
            if (even) {
                curve = Math.floor(-(index / 2)) - 3
            } else {
                curve = Math.floor((index + 1) / 2) + 2
            }

            link.curve = curve * 0.1

            const radius = NODE_SIZE * link.curve * 6.2;
            const angleOffset = -Math.PI / 4; // 45 degrees offset for text alignment
            const textX = start.x + radius * Math.cos(angleOffset);
            const textY = start.y + radius * Math.sin(angleOffset);

            ctx.save();
            ctx.translate(textX, textY);
            ctx.rotate(-angleOffset);
        } else {
            if (even) {
                curve = Math.floor(-(index / 2))
            } else {
                curve = Math.floor((index + 1) / 2)
            }

            link.curve = curve * 0.1

            const midX = (start.x + end.x) / 2 + (end.y - start.y) * (link.curve / 2);
            const midY = (start.y + end.y) / 2 + (start.x - end.x) * (link.curve / 2);

            let textAngle = Math.atan2(end.y - start.y, end.x - start.x)

            // maintain label vertical orientation for legibility
            if (textAngle > Math.PI / 2) textAngle = -(Math.PI - textAngle);
            if (textAngle < -Math.PI / 2) textAngle = -(-Math.PI - textAngle);

            ctx.save();
            ctx.translate(midX, midY);
            ctx.rotate(textAngle);
        }

        // add label
        ctx.globalAlpha = 1;
        ctx.fillStyle = 'black';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '2px Arial';
        ctx.fillText(link.relationship, 0, 0);
        ctx.restore()
    }, [graph.Elements.links])

    const linkPointerAreaPaint = useCallback((link: GraphLink, color: string, ctx: CanvasRenderingContext2D) => {
        const start = link.source;
        const end = link.target;

        if (!start.x || !start.y || !end.x || !end.y) return

        ctx.fillStyle = color;

        // Calculate curve the same way as linkCanvasObject
        const sameNodesLinks = graph.Elements.links.filter(l => (l.source === start.id && l.target === end.id) || (l.target === start.id && l.source === end.id))
        const index = sameNodesLinks.findIndex(l => l.id === link.id) || 0
        const even = index % 2 === 0
        let curve

        if (start.id === end.id) {
            // Self-loop: draw clickable area at the loop position
            if (even) {
                curve = Math.floor(-(index / 2)) - 3
            } else {
                curve = Math.floor((index + 1) / 2) + 2
            }

            const curvature = curve * 0.1
            const radius = NODE_SIZE * curvature * 6.2;
            const angleOffset = -Math.PI / 4;
            const textX = start.x + radius * Math.cos(angleOffset);
            const textY = start.y + radius * Math.sin(angleOffset);

            ctx.beginPath();
            ctx.arc(textX, textY, 5, 0, 2 * Math.PI, false);
            ctx.fill();
        } else {
            // Regular link: draw clickable area at the curve midpoint
            if (even) {
                curve = Math.floor(-(index / 2))
            } else {
                curve = Math.floor((index + 1) / 2)
            }

            const curvature = curve * 0.1
            const midX = (start.x + end.x) / 2 + (end.y - start.y) * (curvature / 2);
            const midY = (start.y + end.y) / 2 + (start.x - end.x) * (curvature / 2);

            ctx.beginPath();
            ctx.arc(midX, midY, 5, 0, 2 * Math.PI, false);
            ctx.fill();
        }
    }, [graph.Elements.links])

    return (
        <div className="relative w-full md:h-full h-1 grow">
            <div className="md:hidden absolute bottom-4 right-4 z-10">
                <button className='control-button' onClick={() => canvasRef.current?.zoomToFit()}>
                    <Fullscreen />
                </button>
            </div>
            <ForceGraph
                data={data}
                canvasRef={canvasRef}
                onNodeClick={screenSize > Number(process.env.NEXT_PUBLIC_MOBILE_BREAKPOINT) || isShowPath ? (node: Node, _evt: MouseEvent) => handleNodeClick(node) : (node: Node, evt: MouseEvent) => handleRightClick(node, evt)}
                onNodeRightClick={handleRightClick}
                onLinkClick={screenSize > Number(process.env.NEXT_PUBLIC_MOBILE_BREAKPOINT) && isPathResponse ? handleLinkClick : handleRightClick}
                onLinkRightClick={handleRightClick}
                onBackgroundClick={unsetSelectedObjects}
                onBackgroundRightClick={unsetSelectedObjects}
                onZoom={() => unsetSelectedObjects()}
                onEngineStop={handleEngineStop}
                nodeCanvasObject={nodeCanvasObject}
                nodePointerAreaPaint={nodePointerAreaPaint}
                linkCanvasObject={linkCanvasObject}
                linkPointerAreaPaint={linkPointerAreaPaint}
                cooldownTicks={cooldownTicks}
            />
        </div>
    )
}