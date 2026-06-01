import { useState } from "react";
import { ChevronDown, Circle, Download, Fullscreen, Pause, Pin, PinOff, Play, ZoomIn, ZoomOut } from "lucide-react";
import type { LayoutMode, HierarchyDirection, RadialDirection } from "@falkordb/canvas";
import { cn } from "@/lib/utils"
import { GraphRef } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
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

interface Props {
    canvasRef: GraphRef
    className?: string
    handleDownloadImage?: () => void
    animation: boolean
    setAnimation: (animation: boolean) => void
}

export function Toolbar({ canvasRef, className, handleDownloadImage, animation, setAnimation }: Props) {

    const [layout, setLayout] = useState<LayoutMode>('force');
    const [direction, setDirection] = useState<string>('');
    const [pinned, setPinned] = useState(false);

    const handleZoomClick = (changefactor: number) => {
        const canvas = canvasRef.current

        if (canvas) {
            canvas.zoom(canvas.getZoom() * changefactor)
        }
    }

    const handleCenterClick = () => {
        const canvas = canvasRef.current

        if (canvas) {
            canvas.zoomToFit()
        }
    }

    const handleAnimationToggle = () => {
        setAnimation(!animation)
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
            const dir = direction || 'td';
            setDirection(dir);
            canvasRef.current?.setLayoutOptions({ tree: { direction: dir as HierarchyDirection } });
        } else if (mode === 'radial') {
            const dir = direction || 'out';
            setDirection(dir);
            canvasRef.current?.setLayoutOptions({ radial: { direction: dir as RadialDirection } });
        } else {
            setDirection('');
        }

        canvasRef.current?.setLayout(mode);

        // Non-force layouts auto-pin
        const nextPinned = mode !== 'force';
        setPinned(nextPinned);
        canvasRef.current?.setPinOnDragEnd(nextPinned);
    }

    const handleDirectionChange = (value: string, targetLayout?: string) => {
        const effectiveLayout = targetLayout || layout;
        setDirection(value);

        if (effectiveLayout === 'tree') {
            canvasRef.current?.setLayoutOptions({ tree: { direction: value as HierarchyDirection } });
        } else if (effectiveLayout === 'radial') {
            canvasRef.current?.setLayoutOptions({ radial: { direction: value as RadialDirection } });
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
            />
            <button
                className="control-button p-1"
                onClick={handlePinToggle}
                title={pinned ? "Unpin nodes" : "Pin nodes on drag"}
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
                                    className={cn("pl-8 relative", layout === 'tree' && direction === d.value ? 'bg-accent' : '')}
                                    onSelect={() => {
                                        if (layout !== 'tree') handleLayoutChange('tree');
                                        handleDirectionChange(d.value, 'tree');
                                    }}
                                >
                                    {layout === 'tree' && direction === d.value && (
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
                                    className={cn("pl-8 relative", layout === 'radial' && direction === d.value ? 'bg-accent' : '')}
                                    onSelect={() => {
                                        if (layout !== 'radial') handleLayoutChange('radial');
                                        handleDirectionChange(d.value, 'radial');
                                    }}
                                >
                                    {layout === 'radial' && direction === d.value && (
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
            <button
                className="control-button"
                onClick={() => handleZoomClick(0.9)}
                title="Zoom Out"
            >
                <ZoomOut size={16} />
            </button>
            <button
                className="control-button"
                onClick={() => handleCenterClick()}
                title="Center"
            >
                <Fullscreen size={16} />
            </button>
            <button
                className="control-button"
                onClick={() => handleZoomClick(1.1)}
                title="Zoom In"
            >
                <ZoomIn size={16} />
            </button>
            <button
                className="hidden md:block control-button"
                title="downloadImage"
                onClick={handleDownloadImage}
            >
                <Download size={16} />
            </button>
        </div>
    )
}