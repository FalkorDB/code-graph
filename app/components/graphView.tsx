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
    id: "desktop" | "mobile"
    selectedObj: Node | Link | undefined
    setSelectedObj: Dispatch<SetStateAction<Node | Link | undefined>>
    selectedObjects: Node[]
    setSelectedObjects: Dispatch<SetStateAction<Node[]>>
    setPosition: Dispatch<SetStateAction<Position | undefined>>
    handleExpand: (nodes: Node[], expand: boolean) => void
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
    id,
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
    const [hoverElement, setHoverElement] = useState<Node | Link | null>()

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

    const handleNodeHover = useCallback((node: Node | null) => {
        setHoverElement(node)
    }, [])

    const handleLinkHover = useCallback((link: Link | null) => {
        setHoverElement(link)
    }, [])

    const isNodeSelected = useCallback((node: GraphNode) => {
        if (isPathResponse) {
            return node.data.isPathSelected
        } else {
            return selectedObjects.some(obj => "category" in obj && obj.id === node.id) || (selectedObj && "category" in selectedObj && selectedObj?.id === node.id) || (hoverElement && ('category' in hoverElement) && hoverElement.id === node.id)
        }
    }, [isPathResponse, selectedObjects, selectedObj, hoverElement])

    const isLinkSelected = useCallback((link: GraphLink) => {
        if (isPathResponse) {
            return link.data.isPathSelected
        } else {
            return selectedObjects.some(obj => "source" in obj && obj.id === link.id) || (selectedObj && "source" in selectedObj && selectedObj?.id === link.id) || (hoverElement && 'source' in hoverElement && hoverElement.id === link.id)
        }
    }, [isPathResponse, selectedObjects, selectedObj, hoverElement])

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
        if (node.x === undefined || node.y === undefined) {
            node.x = 0;
            node.y = 0;
        }

        const isHovered = !!hoverElement && !('source' in hoverElement) && hoverElement.id === node.id
        const isSelected = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id

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
                ctx.lineWidth = isSelected || isHovered ? 1.5 : 1
            }
        } else {
            ctx.fillStyle = node.color;
            ctx.strokeStyle = 'black';
            ctx.lineWidth = isSelected || isHovered ? 1.5 : 1
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_SIZE + ctx.lineWidth / 2, 0, 2 * Math.PI, false);
        ctx.stroke();
        ctx.fill();

        ctx.fillStyle = 'black';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '2px Arial';
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
    }, [selectedObj, selectedObjects, isPathResponse, hoverElement])

    const nodePointerAreaPaint = useCallback((node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
        if (node.x === undefined || node.y === undefined) {
            node.x = 0;
            node.y = 0;
        }

        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_SIZE + 2 + ctx.lineWidth / 2, 0, 2 * Math.PI, false);
        ctx.fill();
    }, [])

    const linkLineDash = useCallback((link: GraphLink) => {
        if (link.data.isPath && !link.data.isPathSelected) return [5, 5]
        return []
    }, [])

    const mobileBreakpointRaw = Number(process.env.NEXT_PUBLIC_MOBILE_BREAKPOINT)
    const mobileBreakpoint = Number.isFinite(mobileBreakpointRaw) ? mobileBreakpointRaw : 0
    const isDesktop = screenSize > mobileBreakpoint

    return (
        <div className="relative w-full md:h-full h-1 grow">
            <div className="md:hidden absolute bottom-4 right-4 z-10">
                <button className='control-button' onClick={() => canvasRef.current?.zoomToFit()}>
                    <Fullscreen />
                </button>
            </div>
            <ForceGraph
                id={id}
                data={data}
                canvasRef={canvasRef}
                onNodeClick={isDesktop || isShowPath ? (node: Node, _evt: MouseEvent) => handleNodeClick(node) : (node: Node, evt: MouseEvent) => handleRightClick(node, evt)}
                onNodeHover={handleNodeHover}
                onNodeRightClick={handleRightClick}
                isNodeSelected={isNodeSelected}
                onLinkClick={isDesktop && isPathResponse ? handleLinkClick : handleRightClick}
                onLinkHover={handleLinkHover}
                onLinkRightClick={handleRightClick}
                isLinkSelected={isLinkSelected}
                onBackgroundClick={unsetSelectedObjects}
                onBackgroundRightClick={unsetSelectedObjects}
                onZoom={() => unsetSelectedObjects()}
                onEngineStop={handleEngineStop}
                nodeCanvasObject={nodeCanvasObject}
                nodePointerAreaPaint={nodePointerAreaPaint}
                linkLineDash={linkLineDash}
                cooldownTicks={cooldownTicks}
            />
        </div>
    )
}