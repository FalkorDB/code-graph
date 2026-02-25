"use client"

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
    onBackgroundClick: (event: MouseEvent) => void
    onBackgroundRightClick: (event: MouseEvent) => void
    nodeCanvasObject: (node: GraphNode, ctx: CanvasRenderingContext2D) => void
    nodePointerAreaPaint: (node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => void
    linkLineDash: (link: any) => number[] | null
    onZoom: () => void
    onEngineStop: () => void
    cooldownTicks: number | undefined
    backgroundColor?: string
    foregroundColor?: string
}

const convertToCanvasData = (graphData: GraphData): Data => ({
    nodes: graphData.nodes.filter(n => n.visible).map(({ id, category, color, visible, isPath, isPathSelected, data }) => ({
        id,
        labels: [category],
        color,
        visible,
        data: { ...data, isPath, isPathSelected }
    })),
    links: graphData.links.filter(l => l.visible).map(({ id, label, color, visible, source, target, isPath, isPathSelected, data }) => ({
        id,
        relationship: label,
        color: isPath ? PATH_COLOR : color,
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
    onBackgroundClick,
    onBackgroundRightClick,
    onZoom,
    onEngineStop,
    nodeCanvasObject,
    nodePointerAreaPaint,
    linkLineDash,
    cooldownTicks,
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

        if (!canvas) return

        (window as any)[id === "desktop" ? "graphDesktop" : "graphMobile"] = () => canvas.getGraphData();
    }, [canvasRef, id])

    // Update canvas colors
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setBackgroundColor(backgroundColor)
        canvasRef.current.setForegroundColor(foregroundColor)
    }, [canvasRef, backgroundColor, foregroundColor, canvasLoaded])

    // Update cooldown ticks
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return

        canvasRef.current.setCooldownTicks(cooldownTicks === -1 ? undefined : cooldownTicks)
    }, [canvasRef, cooldownTicks, canvasLoaded])

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
            autoStopOnSettle: false,
            // nodes will display node.data.captionsKeys in the canvas
            captionsKeys: ["name", "title"],
            onNodeClick: handleNodeClick,
            onNodeRightClick: handleNodeRightClick,
            onNodeHover: handleNodeHover,
            isNodeSelected: isNodeSelected,
            onLinkClick: handleLinkClick,
            onLinkRightClick: handleLinkRightClick,
            onLinkHover: handleLinkHover,
            isLinkSelected: isLinkSelected,
            onBackgroundClick,
            onBackgroundRightClick,
            onEngineStop: handleEngineStop,
            node: { nodeCanvasObject, nodePointerAreaPaint },
            linkLineDash,
            onZoom
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
        onBackgroundClick,
        onBackgroundRightClick,
        handleEngineStop,
        nodeCanvasObject,
        nodePointerAreaPaint,
        linkLineDash,
        onZoom,
        canvasRef,
        canvasLoaded
    ])

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
