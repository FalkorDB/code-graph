import { CircleDot, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils"
import { MutableRefObject } from "react";

export function Toolbar(params: {
    chartRef: MutableRefObject<any>, className?: string
}) {

    function handleZoomClick(changefactor: number) {
        let chart = params.chartRef.current
        if (chart) {
            chart.zoom(chart.zoom() * changefactor)
        }
    }

    return (
        <div className={cn("bg-white flex flex-row rounded overflow-hidden", params.className)}>
            <button
                className="border p-2"
                onClick={() => handleZoomClick(0.9)}
                title="Zoom Out"
            >
                <Minus />
            </button>
            <button
                className="border p-2"
                onClick={() => params.chartRef?.current?.zoomToFit(500, 200)}
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