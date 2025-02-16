import { CircleDot, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils"
import { ForceGraphMethods } from "react-force-graph-2d";
import { Node, Link } from "./model";
import { MutableRefObject } from "react";

interface Props {
    chartRef: MutableRefObject<ForceGraphMethods<Node, Link>>
    className?: string
}

export function Toolbar({ chartRef, className }: Props) {

    const handleZoomClick = (changefactor: number) => {
        const chart = chartRef.current
        if (chart) {
            chart.zoom(chart.zoom() * changefactor)
        }
    }

    const handleCenterClick = () => {
        const chart = chartRef.current
        if (chart) {
            chart.zoomToFit(1000, 40)
        }
    }

    return (
        <div className={cn("bg-white flex flex-row rounded overflow-hidden", className)}>
            <button
                className="border p-2"
                onClick={() => handleZoomClick(0.9)}
                title="Zoom Out"
            >
                <Minus />
            </button>
            <button
                className="border p-2"
                onClick={() => handleCenterClick()}
                title="Center"
            >
                <CircleDot />
            </button>
            <button
                className="border p-2"
                onClick={() => handleZoomClick(1.1)}
                title="Zoom In"
            >
                <Plus />
            </button>
        </div>
    )
}