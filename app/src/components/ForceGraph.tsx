
import { useCallback, useEffect, useState } from "react"
import type { Data, GraphLink, GraphNode } from "@falkordb/canvas"
import { GraphRef, PATH_COLOR } from "@/lib/utils"
import { GraphData, Link, Node } from "./model"

interface Props {
    id: "desktop" | "mobile"
    data: GraphData
    canvasRef: GraphRef
    onNodeClick: (node: Node, event: MouseEvent) => void
    onNodeHover: (node: Node | null) => void
    onNodeRightClick: (node: Node, event: MouseEvent) => void
    isNodeSelected: (node: GraphNode) => boolean
    onLinkClick: (link: Link, event: MouseEvent) => void
    onLinkHover: (link: Link | null) => void
    onLinkRightClick: (link: Link, event: MouseEvent) => void
    isLinkSelected: (link: GraphLink) => boolean
    isNodeDimmed: (node: GraphNode) => boolean
    isLinkDimmed: (link: GraphLink) => boolean
    dimmed: boolean
    linkLineDash: (link: any) => number[]
    onBackgroundClick: (event: MouseEvent) => void
    onBackgroundRightClick: (event: MouseEvent) => void
    onZoom: () => void
    onEngineStop: () => void
    onNodeDragEnd?: () => void
    backgroundColor?: string
    foregroundColor?: string
}


export const convertToCanvasData = (graphData: GraphData): Data => ({
    nodes: graphData.nodes.map(({ id, category, color, visible, expand, isPath, isPathSelected, data }) => ({
        id,
        labels: [category],
        color,
        borderColor: (isPath || isPathSelected) ? PATH_COLOR : undefined,
        visible,
        expand,
        data: { ...data, isPath, isPathSelected }
    })),
    links: graphData.links.map(({ id, label, color, visible, source, target, isPath, isPathSelected, data }) => ({
        id,
        relationship: label,
        color: (isPath || isPathSelected) ? PATH_COLOR : color,
        visible,
        source,
        target,
        data: { ...data, isPath, isPathSelected }
    }))
});

export default function ForceGraph({
    id,
    data,
    canvasRef,
    onNodeClick,
    onNodeHover,
    onNodeRightClick,
    isNodeSelected,
    onLinkClick,
    onLinkHover,
    onLinkRightClick,
    isLinkSelected,
    isNodeDimmed,
    isLinkDimmed,
    dimmed,
    linkLineDash,
    onBackgroundClick,
    onBackgroundRightClick,
    onZoom,
    onEngineStop,
    onNodeDragEnd,
    backgroundColor = "#FFFFFF",
    foregroundColor = "#000000"
}: Props) {
    const [canvasLoaded, setCanvasLoaded] = useState(false)

    // Load falkordb-canvas dynamically (client-only)
    useEffect(() => {
        import('@falkordb/canvas').then(() => {
            setCanvasLoaded(true)
        })
    }, [])

    useEffect(() => {
        const canvas = canvasRef.current

        if (!canvas || !canvasLoaded) return

        (window as any)[id === "desktop" ? "graphDesktop" : "graphMobile"] = () => canvas.getGraphData();
    }, [canvasRef, id, canvasLoaded])

    // Update canvas colors
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setBackgroundColor(backgroundColor)
        canvasRef.current.setForegroundColor(foregroundColor)
    }, [canvasRef, backgroundColor, foregroundColor, canvasLoaded])

    // Map node click handler
    const handleNodeClick = useCallback((node: GraphNode, event: MouseEvent) => {
        const originalNode = data.nodes.find(n => n.id === node.id)
        if (originalNode) onNodeClick(originalNode, event)
    }, [onNodeClick, data.nodes])

    // Map node hover handler
    const handleNodeHover = useCallback((node: GraphNode | null) => {
        if (!node) {
            onNodeHover(null)
            return
        }

        const originalNode = data.nodes.find(n => n.id === node.id)

        if (originalNode) onNodeHover(originalNode)
    }, [onNodeHover, data.nodes])

    // Map node right click handler
    const handleNodeRightClick = useCallback((node: GraphNode, event: MouseEvent) => {
        const originalNode = data.nodes.find(n => n.id === node.id)
        if (originalNode) onNodeRightClick(originalNode, event)
    }, [onNodeRightClick, data.nodes])

    // Map link click handler
    const handleLinkClick = useCallback((link: GraphLink, event: MouseEvent) => {
        const originalLink = data.links.find(l => l.id === link.id)
        if (originalLink) onLinkClick(originalLink, event)
    }, [onLinkClick, data.links])

    // Map link hover handler
    const handleLinkHover = useCallback((link: GraphLink | null) => {
        if (!link) {
            onLinkHover(null)
            return
        }

        const originalLink = data.links.find(l => l.id === link.id)

        if (originalLink) onLinkHover(originalLink)
    }, [onLinkHover, data.links])

    // Map link right click handler
    const handleLinkRightClick = useCallback((link: GraphLink, event: MouseEvent) => {
        const originalLink = data.links.find(l => l.id === link.id)
        if (originalLink) onLinkRightClick(originalLink, event)
    }, [onLinkRightClick, data.links])

    // Handle engine stop and set window.graph
    const handleEngineStop = useCallback(() => {
        onEngineStop()
    }, [canvasRef, onEngineStop])

    // Update event handlers
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setConfig({
            captionsKeys: [["name", true], ["title", true]],
            isNodeSelected: isNodeSelected,
            isLinkSelected: isLinkSelected,
            isNodeDimmed: isNodeDimmed,
            isLinkDimmed: isLinkDimmed,
            linkLineDash,
            eventHandlers: {
                onNodeClick: handleNodeClick,
                onNodeRightClick: handleNodeRightClick,
                onNodeHover: handleNodeHover,
                onLinkClick: handleLinkClick,
                onLinkRightClick: handleLinkRightClick,
                onLinkHover: handleLinkHover,
                onBackgroundClick,
                onBackgroundRightClick,
                onEngineStop: handleEngineStop,
                onNodeDragEnd,
                onZoom
            }
        })
    }, [
        handleNodeClick,
        handleNodeRightClick,
        handleNodeHover,
        handleLinkClick,
        handleLinkRightClick,
        handleLinkHover,
        isNodeSelected,
        isLinkSelected,
        isNodeDimmed,
        isLinkDimmed,
        onBackgroundClick,
        onBackgroundRightClick,
        handleEngineStop,
        onNodeDragEnd,
        linkLineDash,
        onZoom,
        canvasRef,
        canvasLoaded
    ])

    // Sync dimmed state to canvas (like browser: separate effect, not via setConfig)
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setDimmed(dimmed)
    }, [dimmed, canvasRef, canvasLoaded])

    // Update canvas data
    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas || !canvasLoaded) return

        const canvasData = convertToCanvasData(data)
        canvas.setData(canvasData)
    }, [canvasRef, data, canvasLoaded])

    return (
        <falkordb-canvas ref={canvasRef} node-mode="replace" />
    )
}
