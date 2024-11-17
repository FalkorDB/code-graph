import { CircleDot, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils"

export function Toolbar(params: {
    chartRef: React.RefObject<cytoscape.Core>, className?: string
}) {

    function handleZoomClick(changefactor: number) {
        let chart = params.chartRef.current
        if (chart) {
            chart.zoom(chart.zoom() * changefactor)
        }
    }

    function handleCenterClick() {
        let chart = params.chartRef.current
        if (chart) {
            chart.fit(undefined, 80)
            chart.center()
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