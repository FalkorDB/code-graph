import { useState } from "react";
import { ChevronDown, Circle, Download, Fullscreen, Pause, Pin, PinOff, Play, Telescope, ZoomIn, ZoomOut } from "lucide-react";
import type { LayoutMode, HierarchyDirection, RadialDirection } from "@falkordb/canvas";
import { cn } from "@/lib/utils"
import { GraphRef } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import type { Node, Link } from "./model";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

const LAYOUTS: { value: LayoutMode; label: string }[] = [
    { value: 'force', label: 'Force' },
    { value: 'tree', label: 'Tree' },
    { value: 'radial', label: 'Radial' },
];

const HIERARCHY_DIRECTIONS: { value: HierarchyDirection; label: string }[] = [
    { value: 'td', label: 'Top → Down' },
    { value: 'bu', label: 'Bottom → Up' },
    { value: 'lr', label: 'Left → Right' },
    { value: 'rl', label: 'Right → Left' },
];

const RADIAL_DIRECTIONS: { value: RadialDirection; label: string }[] = [
    { value: 'out', label: 'Outward' },
    { value: 'in', label: 'Inward' },
];

interface ZoomControlsProps {
    canvasRef: GraphRef
    className?: string
    selectedObjects?: (Node | Link)[]
}

export function ZoomControls({ canvasRef, className, selectedObjects }: ZoomControlsProps) {
    const handleZoomClick = (changefactor: number) => {
        const canvas = canvasRef.current
        if (!canvas) return
        if (selectedObjects && selectedObjects.length > 0) {
            const graphData = canvas.getGraphData()
            const selectedNodeIds = new Set<number>()
            for (const el of selectedObjects) {
                if ('source' in el) {
                    selectedNodeIds.add(el.source as number)
                    selectedNodeIds.add(el.target as number)
                } else {
                    selectedNodeIds.add(el.id)
                }
            }
            const focusedNodes = graphData?.nodes.filter(n => selectedNodeIds.has(n.id)) ?? []
            if (focusedNodes.length > 0) {
                const cx = focusedNodes.reduce((s, n) => s + (n.x ?? 0), 0) / focusedNodes.length
                const cy = focusedNodes.reduce((s, n) => s + (n.y ?? 0), 0) / focusedNodes.length
                canvas.centerAt(cx, cy, 300)
            }
        }
        canvas.zoom(canvas.getZoom() * changefactor)
    }

    return (
        <div className={cn("flex flex-row items-center gap-1", className)}>
            <button className="control-button" onClick={() => handleZoomClick(0.9)} title="Zoom Out" aria-label="Zoom Out">
                <ZoomOut size={16} />
            </button>
            <button className="control-button" onClick={() => canvasRef.current?.zoomToFit()} title="Center" aria-label="Center">
                <Fullscreen size={16} />
            </button>
            <button className="control-button" onClick={() => handleZoomClick(1.1)} title="Zoom In" aria-label="Zoom In">
                <ZoomIn size={16} />
            </button>
        </div>
    )
}

interface Props {
    canvasRef: GraphRef
    className?: string
    handleDownloadImage?: () => void
    animation: boolean
    setAnimation: (animation: boolean) => void
    manualDimmed: boolean
    setManualDimmed: (dimmed: boolean) => void
    selectedObjects?: (Node | Link)[]
    /** Hide the three zoom buttons, show everything else. */
    hideZoom?: boolean
}

export function Toolbar({ canvasRef, className, handleDownloadImage, animation, setAnimation, manualDimmed, setManualDimmed, selectedObjects, hideZoom: hideZoom }: Props) {

    const [layout, setLayout] = useState<LayoutMode>('force');
    const [treeDirection, setTreeDirection] = useState<HierarchyDirection>('td');
    const [radialDirection, setRadialDirection] = useState<RadialDirection>('out');
    const [pinned, setPinned] = useState(false);

    const handleAnimationToggle = (checked: boolean) => {
        setAnimation(checked);
        canvasRef.current?.setAnimation(checked);
    }

    const handleDimToggle = (checked: boolean) => {
        setManualDimmed(checked);
        canvasRef.current?.setDimmed(checked);
    }

    const handlePinToggle = () => {
        const next = !pinned;
        setPinned(next);
        canvasRef.current?.setPinOnDragEnd(next);
    }

    const handleLayoutChange = (value: string) => {
        const mode = value as LayoutMode;
        setLayout(mode);

        if (mode === 'tree') {
            canvasRef.current?.setLayoutOptions({ tree: { direction: treeDirection } });
        } else if (mode === 'radial') {
            canvasRef.current?.setLayoutOptions({ radial: { direction: radialDirection } });
        }

        canvasRef.current?.setLayout(mode);

        // Non-force layouts auto-pin and auto-disable animation
        const nextPinned = mode !== 'force';
        setPinned(nextPinned);
        canvasRef.current?.setPinOnDragEnd(nextPinned);
        
        // If switching to non-force layout, disable animation
        if (mode !== 'force' && animation) {
            setAnimation(false);
            canvasRef.current?.setAnimation(false);
        }
    }

    const handleDirectionChange = (value: string, targetLayout?: string) => {
        const effectiveLayout = targetLayout || layout;

        if (effectiveLayout === 'tree') {
            const direction = value as HierarchyDirection;
            setTreeDirection(direction);
            canvasRef.current?.setLayoutOptions({ tree: { direction } });
        } else if (effectiveLayout === 'radial') {
            const direction = value as RadialDirection;
            setRadialDirection(direction);
            canvasRef.current?.setLayoutOptions({ radial: { direction } });
        }
    }

    const animationDisabled = pinned || layout !== 'force';

    return (
        <div className={cn("flex flex-row items-center rounded overflow-hidden p-1 gap-1", className)}>
            {animation ? <Pause size={16} /> : <Play size={16} />}
            <Switch
                className="pointer-events-auto data-[state=unchecked]:bg-border"
                checked={animation}
                disabled={animationDisabled}
                onCheckedChange={handleAnimationToggle}
                aria-label={animation ? "Pause animation" : "Play animation"}
            />
            <Telescope size={16} />
            <Switch
                className="pointer-events-auto data-[state=unchecked]:bg-border"
                checked={manualDimmed}
                onCheckedChange={handleDimToggle}
                aria-label="Toggle dimming"
            />
            <button
                className="control-button p-1"
                onClick={handlePinToggle}
                title={pinned ? "Unpin nodes" : "Pin nodes on drag"}
                aria-label={pinned ? "Unpin nodes" : "Pin nodes on drag"}
            >
                {pinned ? <Pin size={16} /> : <PinOff size={16} />}
            </button>
            <div className="h-4 w-px bg-border rounded-full" />
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        type="button"
                        className="flex items-center gap-1 text-sm pointer-events-auto rounded-md px-2 py-1 hover:bg-secondary"
                    >
                        {LAYOUTS.find(l => l.value === layout)?.label}
                        <ChevronDown size={14} />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="center">
                    <DropdownMenuRadioGroup value={layout} onValueChange={handleLayoutChange}>
                        <DropdownMenuRadioItem value="force">Force</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="pl-8 relative">
                            {layout === 'tree' && (
                                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                                    <Circle className="h-2 w-2 fill-current" />
                                </span>
                            )}
                            Tree
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent>
                            {HIERARCHY_DIRECTIONS.map(d => (
                                <DropdownMenuItem
                                    key={d.value}
                                    className={cn("pl-8 relative", layout === 'tree' && treeDirection === d.value ? 'bg-accent' : '')}
                                    onSelect={() => {
                                        if (layout !== 'tree') handleLayoutChange('tree');
                                        handleDirectionChange(d.value, 'tree');
                                    }}
                                >
                                    {layout === 'tree' && treeDirection === d.value && (
                                        <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                                            <Circle className="h-2 w-2 fill-current" />
                                        </span>
                                    )}
                                    {d.label}
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="pl-8 relative">
                            {layout === 'radial' && (
                                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                                    <Circle className="h-2 w-2 fill-current" />
                                </span>
                            )}
                            Radial
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent>
                            {RADIAL_DIRECTIONS.map(d => (
                                <DropdownMenuItem
                                    key={d.value}
                                    className={cn("pl-8 relative", layout === 'radial' && radialDirection === d.value ? 'bg-accent' : '')}
                                    onSelect={() => {
                                        if (layout !== 'radial') handleLayoutChange('radial');
                                        handleDirectionChange(d.value, 'radial');
                                    }}
                                >
                                    {layout === 'radial' && radialDirection === d.value && (
                                        <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                                            <Circle className="h-2 w-2 fill-current" />
                                        </span>
                                    )}
                                    {d.label}
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                </DropdownMenuContent>
            </DropdownMenu>
            <div className="h-4 w-px bg-border rounded-full" />
            {!hideZoom && <ZoomControls canvasRef={canvasRef} selectedObjects={selectedObjects} />}
            {handleDownloadImage && (
                <button
                    className="control-button"
                    title="downloadImage"
                    onClick={handleDownloadImage}
                >
                    <Download size={16} />
                </button>
            )}
        </div>
    )
}