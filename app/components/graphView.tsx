import ForceGraph2D from 'react-force-graph-2d';
import { Graph, GraphData, Link, Node } from './model';
import { Dispatch, RefObject, SetStateAction, useEffect, useRef, useState } from 'react';
import { toast } from '@/components/ui/use-toast';
import { Path } from '../page';
import dagre from 'dagre';

export interface Position {
    x: number,
    y: number,
}

interface Props {
    data: GraphData
    setData: Dispatch<SetStateAction<GraphData>>
    graph: Graph
    chartRef: RefObject<any>
    selectedObj: Node | undefined
    setSelectedObj: Dispatch<SetStateAction<Node | undefined>>
    selectedObjects: Node[]
    setSelectedObjects: Dispatch<SetStateAction<Node[]>>
    setPosition: Dispatch<SetStateAction<Position | undefined>>
    onFetchNode: (nodeIds: number[]) => Promise<GraphData>
    deleteNeighbors: (nodes: Node[]) => void
    isShowPath: boolean
    setPath: Dispatch<SetStateAction<Path | undefined>>
    isPathResponse: boolean | undefined
    selectedPathId: number | undefined
    setSelectedPathId: (selectedPathId: number) => void
    cooldownTicks: number | undefined
    setCooldownTicks: Dispatch<SetStateAction<number | undefined>>
    cooldownTime: number | undefined
    setCooldownTime: Dispatch<SetStateAction<number>>
    isTreeLayout: boolean
}

const PATH_COLOR = "#ffde21"
const NODE_SIZE = 6
const PADDING = 2
const DAGRE_NODE_WIDTH = 10
const DAGRE_NODE_HEIGHT = 10
const RANKS = {
    FILE: 0,
    CLASS: 1,
    FUNCTION: 2,
    OTHER: 3
};

export default function GraphView({
    data,
    setData,
    graph,
    chartRef,
    selectedObj,
    setSelectedObj,
    selectedObjects,
    setSelectedObjects,
    setPosition,
    onFetchNode,
    deleteNeighbors,
    isShowPath,
    setPath,
    isPathResponse,
    selectedPathId,
    setSelectedPathId,
    cooldownTicks,
    cooldownTime,
    setCooldownTicks,
    setCooldownTime,
    isTreeLayout
}: Props) {

    const parentRef = useRef<HTMLDivElement>(null)
    const lastClick = useRef<{ date: Date, name: string }>({ date: new Date(), name: "" })
    const [parentWidth, setParentWidth] = useState(0)
    const [parentHeight, setParentHeight] = useState(0)
    const layoutCache = useRef<{key: string, data: GraphData} | null>(null);

    useEffect(() => {
        const handleResize = () => {
            if (!parentRef.current) return
            setParentWidth(parentRef.current.clientWidth)
            setParentHeight(parentRef.current.clientHeight)
        }

        window.addEventListener('resize', handleResize)

        const observer = new ResizeObserver(handleResize)

        if (parentRef.current) {
            observer.observe(parentRef.current)
        }

        return () => {
            window.removeEventListener('resize', handleResize)
            observer.disconnect()
        }
    }, [parentRef])

    useEffect(() => {
        setCooldownTime(4000)
        setCooldownTicks(undefined)
    }, [graph.Id])

    useEffect(() => {
        setCooldownTime(1000)
        setCooldownTicks(undefined)
    }, [graph.getElements().length])

    useEffect(() => {
        if (!isTreeLayout && chartRef.current) {
            data.nodes.forEach(node => {
                node.x = undefined;
                node.y = undefined;
            });
            setData({...data});
            
            chartRef.current.d3ReheatSimulation();
        }
    }, [isTreeLayout]);

    const unsetSelectedObjects = (evt?: MouseEvent) => {
        if (evt?.ctrlKey || (!selectedObj && selectedObjects.length === 0)) return
        setSelectedObj(undefined)
        setSelectedObjects([])
    }

    const handleNodeRightClick = (node: Node, evt: MouseEvent) => {
        if (evt.ctrlKey) {
            if (selectedObjects.some(obj => obj.id === node.id)) {
                setSelectedObjects(selectedObjects.filter(obj => obj.id !== node.id))
                return
            } else {
                setSelectedObjects([...selectedObjects, node])
            }
        } else {
            setSelectedObjects([])
        }

        setSelectedObj(node)
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
            const expand = !node.expand

            if (expand) {
                const elements = await onFetchNode([node.id])

                if (elements.nodes.length === 0) {
                    toast({
                        title: `No neighbors found`,
                        description: `No neighbors found`,
                    })

                    return
                }
            } else {
                deleteNeighbors([node]);
            }

            node.expand = expand

            setSelectedObj(undefined)
            setData({ ...graph.Elements })

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

    const getRank = (node: Node) => {
        switch (node.category) {
            case 'File': return RANKS.FILE;
            case 'Class': return RANKS.CLASS;
            case 'Function': return RANKS.FUNCTION;
            default: return RANKS.OTHER;
        }
    }

    const getDagreLayout = (graphData: GraphData) => {
        if (!graphData?.nodes?.length) return graphData;
        
        const graphKey = JSON.stringify(graphData.nodes.map(n => n.id).join(',') + '|' + graphData.links.map(l => `${l.source.id}-${l.target.id}`).join(','));
        if (layoutCache.current?.key === graphKey) {
            return layoutCache.current.data;
        }

        const g = new dagre.graphlib.Graph();
        g.setGraph({
            rankdir: 'TB',
            nodesep: 10,
            align: 'UL',
            ranker: 'network-simplex',
            ranksep: 100,
            edgesep: 10,
        });
        g.setDefaultEdgeLabel(() => ({}));

        // Group nodes by their category
        const nodesByRank: Record<number, string[]> = {
            [RANKS.FILE]: [],
            [RANKS.CLASS]: [],
            [RANKS.FUNCTION]: [],
            [RANKS.OTHER]: [],
        };

        // First pass: add nodes and collect them by rank
        graphData.nodes.forEach(node => {
            const rank = getRank(node);
            g.setNode(node.id.toString(), {
                width: DAGRE_NODE_WIDTH,
                height: DAGRE_NODE_HEIGHT,
                rank: rank
            });
            nodesByRank[rank].push(node.id.toString());
        });

        // Add same rank constraints
        Object.values(nodesByRank).forEach(rankNodes => {
            if (rankNodes.length > 1) {
                for (let i = 1; i < rankNodes.length; i++) {
                    g.setEdge(rankNodes[i-1], rankNodes[i], {
                        weight: 0,
                        type: 'RANK',
                        style: 'invisible'
                    });
                }
            }
        });

        // Add actual edges after rank constraints
        graphData.links.forEach((link) => {
            g.setEdge(
                link.source.id.toString(),
                link.target.id.toString(),
                { weight: 1, label: link.label }
            );
        });

        try {
            dagre.layout(g);

            // Update node positions
            graphData.nodes.forEach((node) => {
                const nodeWithPos = g.node(node.id.toString());
                if (nodeWithPos) {
                    node.x = nodeWithPos.x;
                    // Force Y position based on rank
                    const rank = getRank(node);
                    node.y = rank * 100; // Use fixed Y positions based on rank
                }
            });

            layoutCache.current = {
                key: graphKey,
                data: graphData
            };

            requestAnimationFrame(() => {
                if (chartRef.current) {
                    chartRef.current.zoomToFit(1000, 40);
                }
            });

        } catch (error) {
            console.error('Error in dagre layout:', error);
        }

        return graphData;
    };

    return (
        <div ref={parentRef} className="relative w-fill h-full">
            <ForceGraph2D
                ref={chartRef}
                height={parentHeight}
                width={parentWidth}
                key={`graph-${isTreeLayout}`}
                graphData={isTreeLayout ? getDagreLayout(data) : data}
                nodeVisibility="visible"
                linkVisibility="visible"
                linkCurvature="curve"
                linkDirectionalArrowRelPos={1}
                linkDirectionalArrowColor={(link) => (link.isPath || link.isPathSelected) ? PATH_COLOR : link.color}
                linkDirectionalArrowLength={(link) => link.source.id === link.target.id ? 0 : (link.id === selectedObj?.id || link.isPathSelected) ? 3 : 2}
                nodeRelSize={NODE_SIZE}
                linkLineDash={(link) => (link.isPath && !link.isPathSelected) ? [5, 5] : []}
                linkColor={(link) => (link.isPath || link.isPathSelected) ? PATH_COLOR : link.color}
                linkWidth={(link) => (link.id === selectedObj?.id || link.isPathSelected) ? 2 : 1}
                nodeCanvasObjectMode={() => 'after'}
                linkCanvasObjectMode={() => 'after'}
                nodeCanvasObject={(node, ctx) => {
                    if (!node.x || !node.y) return

                    if (isPathResponse) {
                        if (node.isPathSelected) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = PATH_COLOR;
                            ctx.lineWidth = 1
                        } else if (node.isPath) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = PATH_COLOR;
                            ctx.lineWidth = 0.5
                        } else {
                            ctx.fillStyle = '#E5E5E5';
                            ctx.strokeStyle = 'gray';
                            ctx.lineWidth = 0.5
                        }
                    } else if (isPathResponse === undefined) {
                        if (node.isPathSelected) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = PATH_COLOR;
                            ctx.lineWidth = 1
                        } else if (node.isPath) {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = PATH_COLOR;
                            ctx.lineWidth = 0.5
                        } else {
                            ctx.fillStyle = node.color;
                            ctx.strokeStyle = 'black';
                            ctx.lineWidth = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id ? 1 : 0.5
                        }
                    } else {
                        ctx.fillStyle = node.color;
                        ctx.strokeStyle = 'black';
                        ctx.lineWidth = selectedObjects.some(obj => obj.id === node.id) || selectedObj?.id === node.id ? 1 : 0.5
                    }

                    ctx.beginPath();
                    ctx.arc(node.x, node.y, NODE_SIZE, 0, 2 * Math.PI, false);
                    ctx.stroke();
                    ctx.fill();

                    ctx.fillStyle = 'black';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.font = '2px Arial';
                    const textWidth = ctx.measureText(node.name).width;
                    const ellipsis = '...';
                    const ellipsisWidth = ctx.measureText(ellipsis).width;
                    const nodeSize = NODE_SIZE * 2 - PADDING;
                    let { name } = { ...node }

                    // truncate text if it's too long
                    if (textWidth > nodeSize) {
                        while (name.length > 0 && ctx.measureText(name).width + ellipsisWidth > nodeSize) {
                            name = name.slice(0, -1);
                        }
                        name += ellipsis;
                    }

                    // add label
                    ctx.fillText(name, node.x, node.y);
                }}
                linkCanvasObject={(link, ctx) => {
                    const start = link.source;
                    const end = link.target;

                    if (!start.x || !start.y || !end.x || !end.y) return

                    if (start.id === end.id) {
                        const radius = NODE_SIZE * link.curve * 6.2;
                        const angleOffset = -Math.PI / 4; // 45 degrees offset for text alignment
                        const textX = start.x + radius * Math.cos(angleOffset);
                        const textY = start.y + radius * Math.sin(angleOffset);

                        ctx.save();
                        ctx.translate(textX, textY);
                        ctx.rotate(-angleOffset);
                    } else {
                        const midX = (start.x + end.x) / 2 + (end.y - start.y) * (link.curve / 2);
                        const midY = (start.y + end.y) / 2 + (start.x - end.x) * (link.curve / 2);

                        let textAngle = Math.atan2(end.y - start.y, end.x - start.x)

                        // maintain label vertical orientation for legibility
                        if (textAngle > Math.PI / 2) textAngle = -(Math.PI - textAngle);
                        if (textAngle < -Math.PI / 2) textAngle = -(-Math.PI - textAngle);

                        ctx.save();
                        ctx.translate(midX, midY);
                        ctx.rotate(textAngle);
                    }

                    ctx.font = '2px Arial';
                    const textWidth = ctx.measureText(link.label).width;

                    ctx.fillStyle = 'white'; // Background color
                    ctx.globalAlpha = 0.8; // Semi-transparent background
                    ctx.fillRect(
                        -textWidth / 2,
                        -2, // -2 approximates half text height
                        textWidth,
                        4 // 4 approximates text height
                    );

                    // add label
                    ctx.globalAlpha = 1;
                    ctx.fillStyle = 'black';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(link.label, 0, 0);
                    ctx.restore()
                }}
                onNodeClick={handleNodeClick}
                onNodeDragEnd={(n, translate) => setPosition(prev => {
                    return prev && { x: prev.x + translate.x * chartRef.current.zoom(), y: prev.y + translate.y * chartRef.current.zoom() }
                })}
                onNodeRightClick={handleNodeRightClick}
                onLinkClick={handleLinkClick}
                onBackgroundRightClick={unsetSelectedObjects}
                onBackgroundClick={unsetSelectedObjects}
                onZoom={() => unsetSelectedObjects()}
                onEngineStop={() => {
                    setCooldownTicks(0)
                    setCooldownTime(0)
                }}
                cooldownTicks={isTreeLayout ? 0 : cooldownTicks}
                cooldownTime={isTreeLayout ? 0 : cooldownTime}
            />
        </div>
    )
}