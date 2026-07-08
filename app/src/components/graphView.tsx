
import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react';
import { Path } from '@/lib/utils';
import { Fullscreen } from 'lucide-react';
import { GraphRef } from '@/lib/utils';
import ForceGraph from './ForceGraph';
import { GraphLink, GraphNode } from '@falkordb/canvas';
import { useTheme } from './theme-provider';

export interface Position {
    x: number,
    y: number,
    zoom?: number,
}

interface Props {
    data: GraphData
    setData: Dispatch<SetStateAction<GraphData>>
    graph: Graph
    chartRef: GraphRef
    id: "desktop" | "mobile"
    selectedObjects: Node[]
    setSelectedObjects: Dispatch<SetStateAction<Node[]>>
    setPosition: Dispatch<SetStateAction<Position | undefined>>
    handleExpand: (nodes: Node[], expand: boolean) => void
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    isPathResponse: boolean | undefined
    selectedPathId: number | undefined
    setSelectedPathId: (selectedPathId: number) => void
    setZoomedNodes: Dispatch<SetStateAction<Node[]>>
    zoomedNodes: Node[]
    manualDimmed: boolean
}

const LIGHT_CANVAS_BACKGROUND = '#FFFFFF';
const DARK_CANVAS_BACKGROUND = '#1A1A1A';
const LIGHT_CANVAS_FOREGROUND = '#000000';
const DARK_CANVAS_FOREGROUND = '#F5F5F5';

const DOUBLE_CLICK_MS = 300;

export default function GraphView({
    data,
    graph,
    chartRef: canvasRef,
    id,
    selectedObjects,
    setSelectedObjects,
    setPosition,
    handleExpand,
    isShowPath,
    setPath,
    isPathResponse,
    selectedPathId,
    setSelectedPathId,
    zoomedNodes,
    setZoomedNodes,
    manualDimmed
}: Props) {

    const lastClick = useRef<{ date: number, id: number }>({ date: 0, id: 0 })
    const isCenteringRef = useRef(false)
    const [screenSize, setScreenSize] = useState<number>(0)
    const [hoverElement, setHoverElement] = useState<Node | Link | null>()
    const { resolvedTheme } = useTheme()
    const isDark = resolvedTheme === 'dark'
    const canvasBackgroundColor = isDark ? DARK_CANVAS_BACKGROUND : LIGHT_CANVAS_BACKGROUND
    const canvasForegroundColor = isDark ? DARK_CANVAS_FOREGROUND : LIGHT_CANVAS_FOREGROUND

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
        if (evt?.ctrlKey || selectedObjects.length === 0) return
        setSelectedObjects([])
    }, [selectedObjects, setSelectedObjects])

    const handleRightClick = useCallback((element: Node | Link, evt: MouseEvent) => {
        if (evt.ctrlKey && "category" in element) {
            if (selectedObjects.some(obj => obj.id === element.id)) {
                setSelectedObjects(selectedObjects.filter(obj => obj.id !== element.id))
                return
            } else {
                setSelectedObjects([...selectedObjects, element as Node])
            }
        } else {
            setSelectedObjects([element as Node])
        }

        // Center on node or link midpoint when focus mode is ON, then show menu
        if ((manualDimmed || isPathResponse) && canvasRef.current) {
            // Clear any existing menu immediately so it doesn't flash at old position
            setPosition(undefined)

            const graphData = canvasRef.current.getGraphData()
            let cx: number | undefined
            let cy: number | undefined

            if ("category" in element) {
                const graphNode = graphData?.nodes.find(n => n.id === element.id)
                cx = graphNode?.x
                cy = graphNode?.y
            } else {
                const src = graphData?.nodes.find(n => n.id === (element as Link).source)
                const tgt = graphData?.nodes.find(n => n.id === (element as Link).target)
                if (src?.x !== undefined && tgt?.x !== undefined) {
                    cx = ((src.x ?? 0) + (tgt.x ?? 0)) / 2
                    cy = ((src.y ?? 0) + (tgt.y ?? 0)) / 2
                }
            }

            if (cx !== undefined && cy !== undefined) {
                isCenteringRef.current = true
                canvasRef.current.centerAt(cx, cy, 300)
                // Show menu after animation fully settles (400ms > 300ms animation)
                setTimeout(() => {
                    isCenteringRef.current = false
                    const canvasBounds = canvasRef.current?.getBoundingClientRect()
                    if (canvasBounds) {
                        setPosition({
                            x: canvasBounds.left + canvasBounds.width / 2,
                            y: canvasBounds.top + canvasBounds.height / 2,
                            zoom: canvasRef.current?.getZoom() ?? 1
                        })
                    }
                }, 400)
                return
            }
        }
        // Focus mode OFF: use the node's actual screen-center so the gap in
        // elementMenu is always the same fixed value regardless of where on the
        // node the user clicked.
        if ("category" in element && canvasRef.current) {
            const gd = canvasRef.current.getGraphData()
            const gn = gd?.nodes.find(n => n.id === element.id)
            const vp = canvasRef.current.getViewport()
            const cb = canvasRef.current.getBoundingClientRect()
            if (gn?.x !== undefined && gn?.y !== undefined && vp && cb) {
                const z = vp.zoom
                const sx = (gn.x - vp.centerX) * z + cb.width / 2
                const sy = (gn.y - vp.centerY) * z + cb.height / 2
                setPosition({ x: cb.left + sx, y: cb.top + sy, zoom: z })
                return
            }
        }
        setPosition({ x: evt.clientX, y: evt.clientY, zoom: canvasRef.current?.getZoom() ?? 1 })
    }, [selectedObjects, setSelectedObjects, setPosition, canvasRef, manualDimmed, isPathResponse])

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
        }
        // Highlight selected and hovered nodes - dimming handled separately by isNodeDimmed
        return selectedObjects.some(obj => "category" in obj && obj.id === node.id) || (hoverElement && ('category' in hoverElement) && hoverElement.id === node.id)
    }, [isPathResponse, selectedObjects, hoverElement])

    const isLinkSelected = useCallback((link: GraphLink) => {
        if (isPathResponse) {
            return link.data.isPathSelected
        }
        // Highlight selected and hovered links - dimming handled separately by isLinkDimmed
        return selectedObjects.some(obj => "source" in obj && obj.id === link.id) || (hoverElement && 'source' in hoverElement && hoverElement.id === link.id)
    }, [isPathResponse, selectedObjects, hoverElement])

    const handleNodeClick = useCallback(async (node: Node) => {
        const now = Date.now()
        const { date, id } = lastClick.current

        const isDoubleClick = now - date < DOUBLE_CLICK_MS && id === node.id
        lastClick.current = isDoubleClick ? { date: 0, id: 0 } : { date: now, id: node.id }
        
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
    }, [zoomedNodes, canvasRef])

    const isNodeDimmed = useCallback((node: GraphNode) => {
        if (isPathResponse) {
            return !node.data.isPath && !node.data.isPathSelected
        }
        // Only apply dimming when focus mode is ON (manualDimmed=true)
        // When manualDimmed=false, nothing should be dimmed regardless of selection
        if (!manualDimmed) {
            return false
        }
        
        if (selectedObjects.length === 0 && !hoverElement) return false
        
        // Collect all active elements (selected + hovered)
        const activeElements: (Node | Link)[] = [...selectedObjects]
        if (hoverElement && !activeElements.includes(hoverElement)) {
            activeElements.push(hoverElement)
        }
        
        // Build selected node IDs and link endpoint IDs
        const selectedNodeIds = new Set<number>()
        const linkEndpointIds = new Set<number>()
        
        for (const el of activeElements) {
            if (!('source' in el)) {
                selectedNodeIds.add((el as any).id)
            } else {
                linkEndpointIds.add((el as any).source as number)
                linkEndpointIds.add((el as any).target as number)
            }
        }
        
        const allActiveIds = new Set([...selectedNodeIds, ...linkEndpointIds])
        if (allActiveIds.size === 0) return false
        if (allActiveIds.has(node.id)) return false
        
        // Expand neighbourhood only for directly selected nodes
        for (const link of data.links) {
            if ((selectedNodeIds.has(link.source) && link.target === node.id) ||
                (selectedNodeIds.has(link.target) && link.source === node.id)) {
                return false
            }
        }
        
        return true
    }, [isPathResponse, manualDimmed, selectedObjects, hoverElement, data.links])

    const isLinkDimmed = useCallback((link: GraphLink) => {
        if (isPathResponse) {
            return !link.data.isPath && !link.data.isPathSelected
        }
        // Only apply dimming when focus mode is ON (manualDimmed=true)
        // When manualDimmed=false, nothing should be dimmed regardless of selection
        if (!manualDimmed) {
            return false
        }
        
        if (selectedObjects.length === 0 && !hoverElement) return false
        
        // Don't dim the link itself if it's selected/hovered
        if (hoverElement && 'source' in hoverElement && hoverElement.id === link.id) return false
        if (selectedObjects.some(obj => 'source' in obj && obj.id === link.id)) return false
        
        // Collect all active elements (selected + hovered)
        const activeElements: (Node | Link)[] = [...selectedObjects]
        if (hoverElement && !activeElements.includes(hoverElement)) {
            activeElements.push(hoverElement)
        }
        
        // Build selected node IDs only (not link endpoints)
        const selectedNodeIds = new Set<number>()
        for (const el of activeElements) {
            if (!('source' in el)) {
                selectedNodeIds.add((el as any).id)
            }
        }
        
        if (selectedNodeIds.size === 0) return true
        
        // Link is undimmed if one endpoint is a directly selected node
        const srcId = typeof link.source === 'object' ? (link.source as any).id : link.source
        const tgtId = typeof link.target === 'object' ? (link.target as any).id : link.target
        
        if (selectedNodeIds.has(srcId) || selectedNodeIds.has(tgtId)) return false

        return true
    }, [isPathResponse, manualDimmed, selectedObjects, hoverElement, data.links])

    const linkLineDash = useCallback((link: GraphLink) => {
        if (link.data.isPath && !link.data.isPathSelected) return [5, 5]
        return []
    }, [])

    const handleNodeDragEnd = useCallback(() => {
        setPosition(undefined)
    }, [setPosition])

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
                graphId={data.nodes.length === 0 ? '' : graph.Id}
                data={data}
                canvasRef={canvasRef}
                onNodeClick={isDesktop || isShowPath ? (node: Node, _evt: MouseEvent) => handleNodeClick(node) : (node: Node, evt: MouseEvent) => handleRightClick(node, evt)}
                onNodeHover={handleNodeHover}
                onNodeRightClick={handleRightClick}
                isNodeSelected={isNodeSelected}
                onLinkClick={isDesktop ? handleLinkClick : handleRightClick}
                onLinkHover={handleLinkHover}
                onLinkRightClick={handleRightClick}
                isLinkSelected={isLinkSelected}
                isNodeDimmed={isNodeDimmed}
                isLinkDimmed={isLinkDimmed}
                dimmed={isPathResponse === true || manualDimmed}
                linkLineDash={linkLineDash}
                onBackgroundClick={unsetSelectedObjects}
                onBackgroundRightClick={unsetSelectedObjects}
                onZoom={() => { if (!isCenteringRef.current) unsetSelectedObjects() }}
                onEngineStop={handleEngineStop}
                onNodeDragEnd={handleNodeDragEnd}
                backgroundColor={canvasBackgroundColor}
                foregroundColor={canvasForegroundColor}
            />
        </div>
    )
}
