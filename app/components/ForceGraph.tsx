"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { Data } from "@falkordb/canvas"
import { GraphRef } from "@/lib/utils"
import { GraphData, Link, Node } from "./model"

interface Props {
    data: GraphData
    canvasRef: GraphRef
    onNodeClick?: (node: Node, event: MouseEvent) => void
    onNodeRightClick?: (node: Node, event: MouseEvent) => void
    onLinkClick?: (link: Link, event: MouseEvent) => void
    onLinkRightClick?: (link: Link, event: MouseEvent) => void
    onBackgroundClick?: (event: MouseEvent) => void
    onBackgroundRightClick?: (event: MouseEvent) => void
    onZoom?: () => void
    onEngineStop?: () => void
    onNodeDragEnd?: (node: Node, translate: { x: number; y: number }) => void
    cooldownTicks?: number | undefined
    backgroundColor?: string
    foregroundColor?: string
}

const convertToCanvasData = (graphData: GraphData): Data => ({
    nodes: graphData.nodes.filter(n => n.visible).map(({ id, category, color, visible, name, ...data }) => ({
        id,
        labels: [category],
        color,
        visible,
        data: { name, ...data }
    })),
    links: graphData.links.filter(l => l.visible).map(({ id, label, color, visible, source, target, ...data }) => ({
        id,
        relationship: label,
        color,
        visible,
        source,
        target,
        data
    }))
});

export default function ForceGraph({
    data,
    canvasRef,
    onNodeClick,
    onNodeRightClick,
    onLinkClick,
    onLinkRightClick,
    onBackgroundClick,
    onBackgroundRightClick,
    onZoom,
    onEngineStop,
    onNodeDragEnd,
    cooldownTicks,
    backgroundColor = "#FFFFFF",
    foregroundColor = "#000000"
}: Props) {
    const parentRef = useRef<HTMLDivElement>(null)
    const [canvasLoaded, setCanvasLoaded] = useState(false)
    const [parentWidth, setParentWidth] = useState(0)
    const [parentHeight, setParentHeight] = useState(0)

    // Load falkordb-canvas dynamically (client-only)
    useEffect(() => {
        import('@falkordb/canvas').then(() => {
            setCanvasLoaded(true)
        })
    }, [])

    // Handle parent resize
    useEffect(() => {
        const handleResize = () => {
            if (!parentRef.current) return
            setParentWidth(parentRef.current.clientWidth)
            setParentHeight(parentRef.current.clientHeight)
        }

        handleResize()

        const observer = new ResizeObserver(handleResize)
        if (parentRef.current) {
            observer.observe(parentRef.current)
        }

        return () => {
            observer.disconnect()
        }
    }, [])

    // Update canvas dimensions
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setWidth(parentWidth)
        canvasRef.current.setHeight(parentHeight)
    }, [canvasRef, parentWidth, parentHeight, canvasLoaded])

    // Update canvas colors
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setBackgroundColor(backgroundColor)
        canvasRef.current.setForegroundColor(foregroundColor)
    }, [canvasRef, backgroundColor, foregroundColor, canvasLoaded])

    // Update cooldown ticks
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        canvasRef.current.setCooldownTicks(cooldownTicks)
    }, [canvasRef, cooldownTicks, canvasLoaded])

    // Map node click handler
    const handleNodeClick = useCallback((node: any, event: MouseEvent) => {
        if (onNodeClick) {
            const originalNode = data.nodes.find(n => n.id === node.id)
            if (originalNode) onNodeClick(originalNode, event)
        }
    }, [onNodeClick, data.nodes])

    // Map node right click handler
    const handleNodeRightClick = useCallback((node: any, event: MouseEvent) => {
        if (onNodeRightClick) {
            const originalNode = data.nodes.find(n => n.id === node.id)
            if (originalNode) onNodeRightClick(originalNode, event)
        }
    }, [onNodeRightClick, data.nodes])

    // Map link click handler
    const handleLinkClick = useCallback((link: any, event: MouseEvent) => {
        if (onLinkClick) {
            const originalLink = data.links.find(l => l.id === link.id)
            if (originalLink) onLinkClick(originalLink, event)
        }
    }, [onLinkClick, data.links])

    // Map link right click handler
    const handleLinkRightClick = useCallback((link: any, event: MouseEvent) => {
        if (onLinkRightClick) {
            const originalLink = data.links.find(l => l.id === link.id)
            if (originalLink) onLinkRightClick(originalLink, event)
        }
    }, [onLinkRightClick, data.links])

    // Update event handlers
    useEffect(() => {
        if (!canvasRef.current || !canvasLoaded) return
        
        canvasRef.current.setConfig({
            onNodeClick: handleNodeClick,
            onNodeRightClick: handleNodeRightClick,
            onLinkClick: handleLinkClick,
            onLinkRightClick: handleLinkRightClick,
            onBackgroundClick,
            onBackgroundRightClick,
            onEngineStop,
            onZoom
        })
    }, [
        handleNodeClick, 
        handleNodeRightClick, 
        handleLinkClick, 
        handleLinkRightClick, 
        onBackgroundClick, 
        onBackgroundRightClick, 
        onEngineStop,
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
        <div ref={parentRef} className="w-full h-full relative">
            <falkordb-canvas ref={canvasRef} />
        </div>
    )
}
