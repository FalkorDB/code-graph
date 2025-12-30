'use client'

import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, SetStateAction, useEffect, useRef, useState } from 'react';
import { Path } from '@/lib/utils';
import { Fullscreen } from 'lucide-react';
import { GraphRef } from '@/lib/utils';
import ForceGraph from './ForceGraph';
import { GraphNode } from '@falkordb/canvas';

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

export default function GraphView({
    data,
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

    const unsetSelectedObjects = (evt?: MouseEvent) => {
        if (evt?.ctrlKey || (!selectedObj && selectedObjects.length === 0)) return
        setSelectedObj(undefined)
        setSelectedObjects([])
    }

    const handleRightClick = (element: Node | Link, evt: MouseEvent) => {
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
    }

    const handleLinkClick = (link: Link, evt: MouseEvent) => {
        unsetSelectedObjects(evt)
        if (!isPathResponse || link.id === selectedPathId) return
        setSelectedPathId(link.id)
    }

    const handleNodeClick = async (node: Node) => {
        const now = new Date()
        const { date, name } = lastClick.current

        const isDoubleClick = now.getTime() - date.getTime() < 1000 && name === node.name
        lastClick.current = { date: now, name: node.name }

        if (isDoubleClick) {
            handleExpand([node], !node.expand)
        } else if (isShowPath) {
            setPath(prev => {
                if (!prev?.start?.name || (prev.end?.name && prev.end?.name !== "")) {
                    return ({ start: { id: Number(node.id), name: node.name } })
                } else {
                    return ({ end: { id: Number(node.id), name: node.name }, start: prev.start })
                }
            })
            return
        }
    }

    const handleEngineStop = () => {
        if (cooldownTicks === 0) return

        canvasRef.current?.zoomToFit(zoomedNodes.length === 1 ? 4 : 1, (n: GraphNode) => zoomedNodes.some(node => node.id === n.id))
        setZoomedNodes([])
        setCooldownTicks(0)
    }

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
                cooldownTicks={cooldownTicks}
            />
        </div>
    )
}