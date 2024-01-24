import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CircleDot, XCircle, ZoomIn, ZoomOut } from "lucide-react";
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
            chart.fit()
            chart.center()
        }
    }

    return (
        <div className={cn("flex flex-row gap-x-2", params.className)}>
            <TooltipProvider>
                <Tooltip>
                    <TooltipTrigger className="text-gray-600 rounded-lg border border-gray-300 p-2" onClick={() => handleZoomClick(1.1)}>
                        <ZoomIn />
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>Zoom In</p>
                    </TooltipContent>
                </Tooltip>
                <Tooltip>
                    <TooltipTrigger className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300 p-2" onClick={() => handleZoomClick(0.9)}>
                        <ZoomOut />
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>Zoom Out</p>
                    </TooltipContent>
                </Tooltip>
                <Tooltip>
                    <TooltipTrigger className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300 p-2" onClick={handleCenterClick}>
                        <CircleDot />
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>Center</p>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>
        </div>
    )
}