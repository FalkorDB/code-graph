
import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react';
import { Path, PATH_COLOR } from '@/lib/utils';
import { Fullscreen } from 'lucide-react';
import { GraphRef } from '@/lib/utils';
import ForceGraph from './ForceGraph';
import { GraphLink, GraphNode, NODE_SIZE, getContrastTextColor, wrapTextForCircularNode } from '@falkordb/canvas';
import { useTheme } from './theme-provider';

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
    animation: boolean
    setZoomedNodes: Dispatch<SetStateAction<Node[]>>
    zoomedNodes: Node[]
}

const PADDING = 2;
const FONT_FAMILY = 'SofiaSans, Arial, sans-serif';
const FONT_WEIGHT_NORMAL = 400;
const FONT_WEIGHT_SELECTED = 700;
const TEXT_FILL_RATIO = 0.85;
const STROKE_WIDTH_SELECTED = 1.5;
const STROKE_WIDTH_UNSELECTED = 0.5;
const LIGHT_CANVAS_BACKGROUND = '#FFFFFF';
const DARK_CANVAS_BACKGROUND = '#1A1A1A';
const LIGHT_CANVAS_FOREGROUND = '#000000';
const DARK_CANVAS_FOREGROUND = '#F5F5F5';
const LIGHT_DIMMED_NODE_FILL = '#E5E5E5';
const DARK_DIMMED_NODE_FILL = '#525252';
const LIGHT_DIMMED_NODE_STROKE = 'gray';
const DARK_DIMMED_NODE_STROKE = '#A3A3A3';

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
    animation,
    zoomedNodes,
    setZoomedNodes
}: Props) {

    const lastClick = useRef<{ date: Date, name: string }>({ date: new Date(), name: "" })
    const [screenSize, setScreenSize] = useState<number>(0)
    const [hoverElement, setHoverElement] = useState<Node | Link | null>()
    const { resolvedTheme } = useTheme()
    const isDark = resolvedTheme === 'dark'
    const canvasBackgroundColor = isDark ? DARK_CANVAS_BACKGROUND : LIGHT_CANVAS_BACKGROUND
    const canvasForegroundColor = isDark ? DARK_CANVAS_FOREGROUND : LIGHT_CANVAS_FOREGROUND
    const dimmedNodeFillColor = isDark ? DARK_DIMMED_NODE_FILL : LIGHT_DIMMED_NODE_FILL
    const dimmedNodeStrokeColor = isDark ? DARK_DIMMED_NODE_STROKE : LIGHT_DIMMED_NODE_STROKE

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
            lastClick.current = { date: now, name: "" }
            handleExpand([node], !node.expand)
        } else if (isShowPath) {
            lastClick.current = { date: now, name: "" }
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
    }, [zoomedNodes, canvasRef])

    const nodeCanvasObject = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D) => {
        if (node.x === undefined || node.y === undefined) {
            node.x = 0;
            node.y = 0;
        }

        const isHovered = !!hoverElement && !('source' in hoverElement) && hoverElement.id === node.id
        const isSelected = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id
        const nodeSelected = isSelected || isHovered

        // --- Determine colors based on path state ---
        if (isPathResponse) {
            if (node.data.isPathSelected) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = STROKE_WIDTH_SELECTED;
            } else if (node.data.isPath) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = STROKE_WIDTH_UNSELECTED;
            } else {
                ctx.fillStyle = dimmedNodeFillColor;
                ctx.strokeStyle = dimmedNodeStrokeColor;
                ctx.lineWidth = STROKE_WIDTH_UNSELECTED;
            }
        } else if (isPathResponse === undefined) {
            if (node.data.isPathSelected) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = STROKE_WIDTH_SELECTED;
            } else if (node.data.isPath) {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = PATH_COLOR;
                ctx.lineWidth = STROKE_WIDTH_UNSELECTED;
            } else {
                ctx.fillStyle = node.color;
                ctx.strokeStyle = canvasForegroundColor;
                ctx.lineWidth = nodeSelected ? STROKE_WIDTH_SELECTED : STROKE_WIDTH_UNSELECTED;
            }
        } else {
            ctx.fillStyle = node.color;
            ctx.strokeStyle = canvasForegroundColor;
            ctx.lineWidth = nodeSelected ? STROKE_WIDTH_SELECTED : STROKE_WIDTH_UNSELECTED;
        }

        const radius = NODE_SIZE + ctx.lineWidth / 2;

        // Draw stroke circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
        ctx.stroke();

        // Draw fill circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_SIZE, 0, 2 * Math.PI, false);
        ctx.fill();

        // Skip labels when zoomed out (large graph optimisation)
        const zoom = ctx.getTransform().a;
        if (zoom < 1) return;

        // --- Draw text (matching canvas logic) ---
        const fillColor = ctx.fillStyle as string;
        ctx.fillStyle = getContrastTextColor(fillColor);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const textRadius = NODE_SIZE - PADDING / 2;
        const name = node.data.name || node.data.title || String(node.id);
        const nodeFontWeight = nodeSelected ? FONT_WEIGHT_SELECTED : FONT_WEIGHT_NORMAL;
        const baseFontSize = 4;

        // Measure at the base size for line-wrapping decisions
        ctx.font = `${nodeFontWeight} ${baseFontSize}px ${FONT_FAMILY}`;
        const [line1, line2] = wrapTextForCircularNode(ctx, name, textRadius);

        let chosenSize = baseFontSize;

        if (TEXT_FILL_RATIO > 0 && !line2) {
            // Auto-size mode: scale text to fill textFillRatio × nodeRadius
            const REF = 20;
            ctx.font = `${nodeFontWeight} ${REF}px ${FONT_FAMILY}`;
            const refMetrics = ctx.measureText(line1);
            const visualWidth = (refMetrics.actualBoundingBoxLeft ?? 0)
                + (refMetrics.actualBoundingBoxRight ?? 0);
            const refWidth = Math.max(visualWidth, refMetrics.width);
            const refHeight = (refMetrics.actualBoundingBoxAscent ?? 0)
                + (refMetrics.actualBoundingBoxDescent ?? 0);

            const r = TEXT_FILL_RATIO * textRadius;
            if (refWidth > 0 && refHeight > 0) {
                const diagonal = Math.sqrt(refWidth * refWidth + refHeight * refHeight);
                chosenSize = REF * (2 * r / diagonal);
            } else if (refWidth > 0) {
                chosenSize = REF * (2 * r / refWidth);
            }
        }

        ctx.font = `${nodeFontWeight} ${chosenSize}px ${FONT_FAMILY}`;

        const textMetrics = ctx.measureText(line1);
        const textHeight = textMetrics.actualBoundingBoxAscent + textMetrics.actualBoundingBoxDescent;
        const halfTextHeight = (textHeight / 2) * 1.5;

        if (line1) {
            const yCorrection = line2
                ? 0
                : (textMetrics.actualBoundingBoxAscent - textMetrics.actualBoundingBoxDescent) / 2;
            ctx.fillText(line1, node.x, line2 ? node.y - halfTextHeight : node.y + yCorrection);
        }
        if (line2) {
            ctx.fillText(line2, node.x, node.y + halfTextHeight);
        }
    }, [
        selectedObj,
        selectedObjects,
        isPathResponse,
        hoverElement,
        dimmedNodeFillColor,
        dimmedNodeStrokeColor,
        canvasForegroundColor,
    ])

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

    const mobileBreakpointRaw = Number(import.meta.env.VITE_MOBILE_BREAKPOINT)
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
                animation={animation}
                backgroundColor={canvasBackgroundColor}
                foregroundColor={canvasForegroundColor}
            />
        </div>
    )
}
