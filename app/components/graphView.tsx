import { ForceGraph2D } from "react-force-graph"
import { Node, Edge, GraphData } from "./model"
import { Dispatch, MutableRefObject, SetStateAction, useEffect } from "react"
import { Path } from "../page"

interface Props {
    height: number
    width: number
    chartRef: MutableRefObject<any>
    data: GraphData
    isShowPath: boolean
    isPathResponse: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    setPosition: (position: { x: number, y: number }) => void
    setSelectedObj: (obj: Node | undefined) => void
    setSelectedPathId: (selectedPathId: string) => void
    handelNodeRightTap: (node: Node) => void
}

export default function GraphView({ height, width, chartRef, data, isShowPath, setPath, setPosition, setSelectedObj, handelNodeRightTap, isPathResponse, setSelectedPathId }: Props) {

    const handelNodeTap = (node: Node, event: MouseEvent) => {

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

        setPosition({ y: event.clientY - 180 + chartRef.current.zoom() * 4, x: event.clientX - 30 });
        setSelectedObj(node)
    }

    const handelLinkTap = (edge: Edge) => {
        setSelectedObj(undefined)

        if (!isPathResponse) return
        setSelectedPathId(edge.id)
    }

    return (
        <div className="relative h-full overflow-hidden">
            <ForceGraph2D
                height={height}
                width={width}
                ref={chartRef}
                graphData={data}
                onNodeClick={handelNodeTap}
                onNodeRightClick={handelNodeRightTap}
                onLinkClick={handelLinkTap}
                onNodeDrag={() => {
                    setSelectedObj(undefined)
                }}
                onZoom={() => {
                    setSelectedObj(undefined)
                }}
                onBackgroundClick={() => {
                    setSelectedObj(undefined)
                }}
                nodeVisibility={"nodeVisibility"}
                linkVisibility={"linkVisibility"}
            />
        </div>
    )
}