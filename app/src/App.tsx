import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Graph, GraphData, Node } from './components/model';
import { AlignRight, BookOpen, BoomBox, Download, Github, HomeIcon, Search, X } from 'lucide-react';
import { ImperativePanelHandle, Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { toast } from '@/components/ui/use-toast';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { prepareArg } from './utils';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { Carousel, CarouselApi, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel';
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle, DrawerTrigger } from '@/components/ui/drawer';
import Input from './components/Input';
import { Labels } from './components/labels';
import { Toolbar, ZoomControls } from './components/toolbar';
import { cn, GraphRef, Message, Path, PathData, PathNode } from '@/lib/utils';
import type { GraphNode } from '@falkordb/canvas';
import { convertToCanvasData } from './components/ForceGraph';
import { Toaster } from '@/components/ui/toaster';
import GTM from './GTM';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ThemeToggle } from './components/theme-toggle';
import Logo from './components/logo';


const Chat = lazy(() => import('./components/chat').then(mod => ({ default: mod.Chat })));
const CodeGraph = lazy(() => import('./components/code-graph').then(mod => ({ default: mod.CodeGraph })));

const AUTH_HEADERS: HeadersInit = import.meta.env.VITE_SECRET_TOKEN
  ? { 'Authorization': `Bearer ${import.meta.env.VITE_SECRET_TOKEN}` }
  : {};

type Tip = {
  title: string
  description: string
  keyboardCommand: string
}

const DESKTOP_TIPS: Tip[] = [
  {
    title: "Select Items in Specific Area",
    description: `Click and drag your mouse over an area to create a selection box.
    Any object within the selection area will be highlighted.
    This is useful for selecting multiple objects at once within a specific region of your design.`,
    keyboardCommand: "Click+Drag"
  },
  {
    title: "Open Menu",
    description: "Right Click on object to open the menu.",
    keyboardCommand: "Right Click"
  },
  {
    title: "Remove Items",
    description: `Press delete to remove the selected object.`,
    keyboardCommand: "Delete"
  },
]
const MOBILE_TIPS: string[] = [
  "By representing data as interconnected nodes and edges, FalkorDB facilitates efficient storage and rapid retrieval",
  "We use an OpenCypher query language with proprietary enhancements that streamline interactions with graph data.",
  "FalkorDB delivers an accurate, multi-tenant RAG solution powered by a low-latency, scalable graph database technology.",
]

export default function App() {

  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [graph, setGraph] = useState(Graph.empty());
  const [selectedValue, setSelectedValue] = useState("");
  const [selectedPathId, setSelectedPathId] = useState<number>();
  const [isPathResponse, setIsPathResponse] = useState<boolean | undefined>(false);
  const [createURL, setCreateURL] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [tipOpen, setTipOpen] = useState(false)
  const [options, setOptions] = useState<string[]>([]);
  const [path, setPath] = useState<Path | undefined>();
  const [isSubmit, setIsSubmit] = useState<boolean>(false);
  const desktopChartRef = useRef<GraphRef["current"]>(null)
  const mobileChartRef = useRef<GraphRef["current"]>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [searchNode, setSearchNode] = useState<PathNode>({});
  const [animation, setAnimation] = useState(false)
  const [manualDimmed, setManualDimmed] = useState<boolean>(true)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([]);
  const [query, setQuery] = useState('');
  const [selectedPath, setSelectedPath] = useState<PathData>();
  const [paths, setPaths] = useState<PathData[]>([]);
  const chatPanel = useRef<ImperativePanelHandle>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [carouselApi, setCarouselApi] = useState<CarouselApi>()
  const [zoomedNodes, setZoomedNodes] = useState<Node[]>([])
  const [hasHiddenElements, setHasHiddenElements] = useState(false);

  useEffect(() => {
    if (path?.start?.id && path?.end?.id) {
      setChatOpen(true)
    }
  }, [path])

  useEffect(() => {
    if (!carouselApi) return

    carouselApi.on('select', () => {
      setActiveIndex(carouselApi.selectedScrollSnap())
    })
  }, [carouselApi])

  async function onCreateRepo(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()

    setIsSubmit(true)

    if (!createURL) {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: "Please enter a URL.",
      })
      return
    }

    const result = await fetch(`/api/analyze_repo`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...AUTH_HEADERS,
      },
      body: JSON.stringify({ repo_url: createURL }),
    })

    if (!result.ok) {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: await result.text(),
      })
      setIsSubmit(false)
      return
    }

    const graphName = createURL.split('/').pop()!

    setOptions(prev => [...prev, graphName])
    setSelectedValue(graphName)
    setCreateURL("")
    setCreateOpen(false)
    setIsSubmit(false)

    toast({
      title: "Success",
      description: `Project ${graphName} created successfully`,
    })
  }

  async function onFetchGraph(graphName: string) {
    try {
      const result = await fetch(`/api/graph_entities?repo=${prepareArg(graphName)}`, {
        method: 'GET',
        headers: {
          ...AUTH_HEADERS,
        },
      })

      if (!result.ok) {
        toast({
          variant: "destructive",
          title: "Uh oh! Something went wrong.",
          description: await result.text(),
        })
        return
      }

      const json = await result.json()
      const g = Graph.create(json.entities, graphName)
      setGraph(g)

      setIsPathResponse(false)
      chatPanel.current?.expand()
      // @ts-ignore
      window.graph = g
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: "Failed to load repository graph. Please try again.",
      })
    }
  }

  // Send the user query to the server to expand a node
  async function onFetchNode(nodeIds: number[]) {

    const result = await fetch(`/api/get_neighbors`, {
      method: 'POST',
      body: JSON.stringify({ node_ids: nodeIds, repo: graph.Id }),
      headers: {
        'Content-Type': 'application/json',
        ...AUTH_HEADERS,
      },
    })

    if (!result.ok) {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: await result.text(),
      })
      return { nodes: [], links: [] }
    }

    const json = await result.json()

    return graph.extend(json.neighbors, true)
  }

  const handleSearchSubmit = async (node: any, canvasRef: GraphRef) => {
    const canvas = canvasRef.current

    if (canvas) {
      let chartNode = graph.Elements.nodes.find(n => n.id == node.id)

      if (!chartNode?.visible) {
        if (!chartNode) {
          chartNode = graph.extend({ nodes: [node], edges: [] }).nodes[0]

          setZoomedNodes([chartNode])
          graph.visibleLinks(true, [chartNode!.id])

          canvas.setGraphData(convertToCanvasData(graph.Elements))

          setTimeout(() => {
            canvas.zoomToFit(4, (n: GraphNode) => n.id === chartNode!.id)
          }, 0)
          setSearchNode(chartNode)
          setOptionsOpen(false)
          return
        }

        chartNode.visible = true
        graph.visibleLinks(true, [chartNode!.id])

        canvas.setGraphData(convertToCanvasData(graph.Elements))
      }

      setTimeout(() => {
        canvas.zoomToFit(4, (n: GraphNode) => n.id === chartNode!.id)
      }, 0)
      setSearchNode(chartNode)
      setOptionsOpen(false)
    }
  }

  function onCategoryClick(name: string, show: boolean, canvasRef: GraphRef) {

    const canvas = canvasRef.current;

    if (!canvas) return

    graph.Categories.find(c => c.name === name)!.show = show

    graph.Elements.nodes.forEach(node => {
      if (node.category !== name) return
      node.visible = show
    })

    graph.visibleLinks(show)

    // setGraphData doesn't update visible for existing nodes — mutate canvas nodes directly
    const canvasData = canvas.getGraphData()
    canvasData.nodes.forEach((canvasNode: { id: number, visible: boolean }) => {
      const appNode = graph.NodesMap.get(canvasNode.id)
      if (appNode) canvasNode.visible = appNode.visible
    })
    canvasData.links.forEach((canvasLink: { id: number, visible: boolean }) => {
      const appLink = graph.LinksMap.get(canvasLink.id)
      if (appLink) canvasLink.visible = appLink.visible
    })
    canvas.refresh()

    setHasHiddenElements(graph.getElements().some(element => !element.visible));
  }

  const handleDownloadImage = async () => {
    try {
      const canvases = Array.from(document.querySelectorAll('falkordb-canvas').values()).map(canvas => canvas.shadowRoot?.querySelector('canvas')).filter((c): c is HTMLCanvasElement => !!c);

      if (canvases.length === 0) {
        toast({
          title: "Error",
          description: "Canvas not found",
          variant: "destructive",
        });
        return;
      }

      const canvas = Array.from(canvases).find(canvas => {
        const container = canvas.parentElement;

        if (!container) return false;

        // Check if element is actually in viewport
        const rect = container.getBoundingClientRect();
        const isInViewport = rect.width > 0 &&
          rect.height > 0 &&
          rect.top >= 0 &&
          rect.left >= 0 &&
          rect.bottom <= window.innerHeight &&
          rect.right <= window.innerWidth;

        return isInViewport;
      })

      if (!canvas) return;

      const dataURL = canvas.toDataURL('image/webp');
      const link = document.createElement('a');
      link.href = dataURL;
      link.download = `${graph.Id}.webp`;
      link.click();
    } catch (error) {
      console.error('Error downloading graph image:', error);
      toast({
        title: "Error",
        description: "Failed to download image. Please try again.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="relative font-sans">
      <GTM />
      <main className="h-[100dvh]">
        <div className='md:flex md:flex-col hidden h-screen' id='desktop'>
          <header className="flex flex-col text-xl">
            <div className="flex items-center justify-between py-2 px-4 border-b border-border">
              <div className="flex gap-4 items-center">
                <a href="https://www.falkordb.com" target='_blank' rel="noopener noreferrer" aria-label="FalkorDB">
                  <Logo />
                </a>
                <h1 className='font-semibold text-[22px]'>
                  CODE GRAPH
                </h1>
              </div>
              <TooltipProvider>
                <ul className="flex gap-1 items-center">
                  <li>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon" asChild>
                          <a title="Home" href="https://www.falkordb.com" target='_blank' rel="noopener noreferrer">
                            <HomeIcon className="h-5 w-5" />
                          </a>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Main Website</TooltipContent>
                    </Tooltip>
                  </li>
                  <li>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon" asChild>
                          <a title="GitHub" href="https://github.com/FalkorDB/code-graph" target='_blank' rel="noopener noreferrer">
                            <Github className="h-5 w-5" />
                          </a>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>GitHub</TooltipContent>
                    </Tooltip>
                  </li>
                  <li>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon" asChild>
                          <a title="Discord" href="https://discord.gg/falkordb" target='_blank' rel="noopener noreferrer">
                            <BoomBox className="h-5 w-5" />
                          </a>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Discord</TooltipContent>
                    </Tooltip>
                  </li>
                  <li>
                    <DropdownMenu open={tipOpen} onOpenChange={setTipOpen}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" title="Tip">
                              <BookOpen className="h-5 w-5" />
                            </Button>
                          </DropdownMenuTrigger>
                        </TooltipTrigger>
                        <TooltipContent>Tips</TooltipContent>
                      </Tooltip>
                      <DropdownMenuContent className='flex-col flex p-4 gap-6 max-w-[30dvw]'>
                        <div className='flex justify-between items-center'>
                          <DropdownMenuLabel className='text-[20px] font-semibold leading-[20px] text-left'>HOW TO USE THE PRODUCT</DropdownMenuLabel>
                          <button
                            title='Close'
                            onClick={() => setTipOpen(false)}
                          >
                            <X />
                          </button>
                        </div>
                        {
                          DESKTOP_TIPS.map((tip, index) => (
                            <div key={index} className='flex flex-col gap-4 text-muted-foreground'>
                              <div className='flex gap-3 items-center'>
                                <h1 className='text-foreground font-bold'>{tip.title}</h1>
                                <p className='bg-secondary p-1 rounded italic'>{tip.keyboardCommand}</p>
                              </div>
                              <p>{tip.description}</p>
                            </div>
                          ))
                        }
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </li>
                  <li>
                    <ThemeToggle />
                  </li>
                  {
                    import.meta.env.VITE_LOCAL_MODE &&
                    <li>
                      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                        <DialogTrigger asChild>
                          <Button title="Create new project">
                            Create new project
                          </Button>
                        </DialogTrigger>
                        <DialogContent className='sm:max-w-[500px]'>
                          <DialogHeader>
                            <DialogTitle>{!isSubmit ? "CREATE A NEW PROJECT" : "THANK YOU FOR A NEW REQUEST"}</DialogTitle>
                          </DialogHeader>
                          <DialogDescription className='text-foreground'>
                            {
                              !isSubmit
                                ? "Please provide the URL of the project to connect and start querying data"
                                : "Processing your graph, this could take a while. We appreciate your patience"
                            }
                          </DialogDescription>
                          {
                            !isSubmit ?
                              <form onSubmit={onCreateRepo} className='flex flex-col gap-4'>
                                <input
                                  className='border p-3 rounded-lg bg-background text-foreground'
                                  type="text"
                                  value={createURL}
                                  onChange={(e) => setCreateURL(e.target.value)}
                                  placeholder="Type Project URL (File:// or https://)"
                                />
                                <div className='flex flex-row-reverse'>
                                  <Button type='submit' title='Create Project'>
                                    Create
                                  </Button>
                                </div>
                              </form>
                              : <Progress value={0} />
                          }
                        </DialogContent>
                      </Dialog>
                    </li>
                  }
                </ul>
              </TooltipProvider>
            </div>
          </header>
          <Suspense fallback={<div className="flex items-center justify-center h-full">Loading...</div>}>
            <PanelGroup direction="horizontal" className="w-full h-full">
              <Panel defaultSize={graph.Id ? 70 : 100} className="flex flex-col" minSize={50}>
                <CodeGraph
                  id="desktop"
                  graph={graph}
                  data={data}
                  setData={setData}
                  canvasRef={desktopChartRef}
                  options={options}
                  setOptions={setOptions}
                  onFetchGraph={onFetchGraph}
                  onFetchNode={onFetchNode}
                  setPath={setPath}
                  isShowPath={!!path}
                  selectedValue={selectedValue}
                  selectedPathId={selectedPathId}
                  setSelectedPathId={setSelectedPathId}
                  isPathResponse={isPathResponse}
                  setIsPathResponse={setIsPathResponse}
                  handleSearchSubmit={(node) => handleSearchSubmit(node, desktopChartRef)}
                  searchNode={searchNode}
                  setSearchNode={setSearchNode}
                  animation={animation}
                  setAnimation={setAnimation}
                  manualDimmed={manualDimmed}
                  setManualDimmed={setManualDimmed}
                  onCategoryClick={(name, show) => onCategoryClick(name, show, desktopChartRef)}
                  handleDownloadImage={handleDownloadImage}
                  zoomedNodes={zoomedNodes}
                  setZoomedNodes={setZoomedNodes}
                  hasHiddenElements={hasHiddenElements}
                  setHasHiddenElements={setHasHiddenElements}
                />
              </Panel>
              <PanelResizeHandle className={cn(!graph.Id && 'hidden', 'w-1 bg-border hover:bg-primary/50 transition-colors')} />
              <Panel
                ref={chatPanel}
                className="border-l"
                defaultSize={graph.Id ? 30 : 0}
                minSize={30}
                maxSize={50}
                collapsible
              >
                <Chat
                  messages={messages}
                  setMessages={setMessages}
                  query={query}
                  setQuery={setQuery}
                  selectedPath={selectedPath}
                  setSelectedPath={setSelectedPath}
                  canvasRef={desktopChartRef}
                  setPath={setPath}
                  path={path}
                  repo={graph.Id}
                  graph={graph}
                  selectedPathId={selectedPathId}
                  isPathResponse={isPathResponse}
                  setIsPathResponse={setIsPathResponse}
                  paths={paths}
                  setPaths={setPaths}
                />
              </Panel>
            </PanelGroup>
          </Suspense>
        </div>
        <div className='flex flex-col md:hidden h-full overflow-hidden' id='mobile'>
          <header className='flex justify-between items-center bg-muted py-2 px-4'>
            <a href="https://www.falkordb.com" target='_blank' rel="noopener noreferrer" aria-label="FalkorDB" className="flex gap-2 items-center">
              <Logo width={40} height={34} />
              <span className='font-semibold text-[22px]'>CODE GRAPH</span>
            </a>
            <div className='flex gap-2'>
              <ThemeToggle />
              <button onClick={() => setMenuOpen(prev => !prev)}>
                <AlignRight />
              </button>
            </div>
          </header>

          {menuOpen && (
            <div className='absolute bottom-0 top-[70px] left-0 right-0 z-20 bg-background shadow-lg'>
              <ul className='h-full flex flex-col gap-16 p-8 items-center'>
                <li>
                  <a href="https://github.com/FalkorDB/code-graph" target='_blank' rel="noopener noreferrer">
                    <p>GitHub</p>
                  </a>
                </li>
                <li>
                  <a href="https://discord.gg/falkordb" target='_blank' rel="noopener noreferrer">
                    <p>Discord</p>
                  </a>
                </li>
                <li>
                  <a href="https://www.falkordb.com" target='_blank' rel="noopener noreferrer">
                    <p>Main Website</p>
                  </a>
                </li>
                <Carousel
                  className='w-[85%]'
                  opts={{
                    align: "center",
                  }}
                  setApi={setCarouselApi}
                >
                  <CarouselContent className='w-full'>
                    {MOBILE_TIPS.map((tip, index) => (
                      <CarouselItem key={index} className='text-center'>
                        <p>{tip}</p>
                      </CarouselItem>
                    ))}
                  </CarouselContent>
                  <div className="flex justify-center gap-2 mt-4">
                    {MOBILE_TIPS.map((_, index) => (
                      <div
                        key={index}
                        className={cn(
                          "h-2 w-2 rounded-full bg-muted-foreground/30",
                          index === activeIndex && "bg-muted-foreground"
                        )}
                      />
                    ))}
                  </div>
                  <CarouselPrevious className='-left-10' />
                  <CarouselNext className='-right-10' />
                </Carousel>
              </ul>
            </div>
          )}
          <Suspense fallback={<div className="flex items-center justify-center h-full">Loading...</div>}>
            <div className='flex flex-col grow'>
              <CodeGraph
                id="mobile"
                graph={graph}
                data={data}
                setData={setData}
                canvasRef={mobileChartRef}
                options={options}
                setOptions={setOptions}
                onFetchGraph={onFetchGraph}
                onFetchNode={onFetchNode}
                setPath={setPath}
                isShowPath={!!path}
                selectedValue={selectedValue}
                selectedPathId={selectedPathId}
                setSelectedPathId={setSelectedPathId}
                isPathResponse={isPathResponse}
                setIsPathResponse={setIsPathResponse}
                handleSearchSubmit={(node) => handleSearchSubmit(node, mobileChartRef)}
                setSearchNode={setSearchNode}
                searchNode={searchNode}
                animation={animation}
                setAnimation={setAnimation}
                manualDimmed={manualDimmed}
                setManualDimmed={setManualDimmed}
                onCategoryClick={(name, show) => onCategoryClick(name, show, mobileChartRef)}
                handleDownloadImage={handleDownloadImage}
                zoomedNodes={zoomedNodes}
                setZoomedNodes={setZoomedNodes}
                hasHiddenElements={hasHiddenElements}
                setHasHiddenElements={setHasHiddenElements}
              />
              {graph.Id && (
                <div className='flex items-center p-4 gap-4'>
                  <Drawer open={chatOpen} onOpenChange={setChatOpen}>
                    <DrawerTrigger asChild>
                      <Button className='grow'>
                        Chat
                      </Button>
                    </DrawerTrigger>
                    <DrawerContent handleClassName='bg-muted-foreground h-1' className='md:hidden flex flex-col h-[90dvh]'>
                      <VisuallyHidden>
                        <DrawerTitle />
                        <DrawerDescription />
                      </VisuallyHidden>
                      <Chat
                        messages={messages}
                        setMessages={setMessages}
                        query={query}
                        setQuery={setQuery}
                        selectedPath={selectedPath}
                        setSelectedPath={setSelectedPath}
                        canvasRef={mobileChartRef}
                        setPath={setPath}
                        path={path}
                        repo={graph.Id}
                        graph={graph}
                        selectedPathId={selectedPathId}
                        isPathResponse={isPathResponse}
                        setIsPathResponse={setIsPathResponse}
                        setChatOpen={setChatOpen}
                        paths={paths}
                        setPaths={setPaths}
                      />
                    </DrawerContent>
                  </Drawer>
                  <Drawer open={optionsOpen} onOpenChange={setOptionsOpen}>
                    <DrawerTrigger asChild>
                      <Button variant="outline" className='grow'>
                        Options
                      </Button>
                    </DrawerTrigger>
                    <DrawerContent handleClassName='mt-0 bg-muted-foreground h-1' overlayClassName='bg-transparent' className='md:hidden flex flex-col gap-8 p-4 items-center bg-secondary border-2 border-border'>
                      <VisuallyHidden>
                        <DrawerTitle />
                        <DrawerDescription />
                      </VisuallyHidden>
                      {/* Zoom controls floating above the drawer handle */}
                      <ZoomControls
                        className='bg-transparent absolute -top-14 left-0 w-full justify-center px-6'
                        canvasRef={mobileChartRef}
                      />
                      <Input
                        className='border-2 border-border'
                        graph={graph}
                        onValueChange={(node) => setSearchNode(node)}
                        icon={<Search />}
                        handleSubmit={(node) => handleSearchSubmit(node, mobileChartRef)}
                        node={searchNode}
                      />
                      <Labels categories={graph.Categories} onClick={(name, show) => onCategoryClick(name, show, mobileChartRef)} />
                      {/* Options controls inside the drawer, below search */}
                      <Toolbar
                        hideZoom
                        className='w-full justify-center'
                        canvasRef={mobileChartRef}
                        animation={animation}
                        setAnimation={setAnimation}
                        manualDimmed={manualDimmed}
                        setManualDimmed={setManualDimmed}
                      />
                    </DrawerContent>
                  </Drawer>
                </div>
              )}
            </div>
          </Suspense>
        </div>
      </main>
      <Toaster />
    </div>
  )
}
