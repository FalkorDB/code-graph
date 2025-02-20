import { CircleDot, Download, Fullscreen, Minus, Plus, ZoomIn, ZoomOut } from "lucide-react";
import { cn } from "@/lib/utils"
import { MutableRefObject } from "react";
import { ForceGraphMethods } from "react-force-graph-2d";
import { Link, Node } from "./model";
interface Props {
    chartRef: MutableRefObject<ForceGraphMethods<Node, Link> | undefined>
    className?: string
    handleDownloadImage?: () => void
}

export function Toolbar({ chartRef, className, handleDownloadImage }: Props) {

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
        <div className={cn("flex flex-row rounded overflow-hidden", className)}>
            <button
                className="control-button"
                onClick={() => handleZoomClick(0.9)}
                title="Zoom Out"
            >
                <ZoomOut />
            </button>
            <button
                className="control-button"
                onClick={() => handleCenterClick()}
                title="Center"
            >
                <Fullscreen />
            </button>
            <button
                className="control-button"
                onClick={() => handleZoomClick(1.1)}
                title="Zoom In"
            >
                <ZoomIn />
            </button>
            <button
                className="hidden md:block control-button"
                onClick={handleDownloadImage}
            >
                <Download />
            </button>
        </div>
    )
}