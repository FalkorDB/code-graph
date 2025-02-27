'use client'

import { MutableRefObject, useEffect, useRef, useState } from 'react';
import { Chat } from './components/chat';
import { Graph, GraphData, Link as LinkType, Node } from './components/model';
import { AlignRight, BookOpen, BoomBox, Download, Github, HomeIcon, Search, X } from 'lucide-react';
import Link from 'next/link';
import { ImperativePanelHandle, Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { CodeGraph } from './components/code-graph';
import { toast } from '@/components/ui/use-toast';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import Image from 'next/image';
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { prepareArg } from './utils';
import { Carousel, CarouselApi, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel';
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle, DrawerTrigger } from '@/components/ui/drawer';
import Input from './components/Input';
import { ForceGraphMethods, NodeObject } from 'react-force-graph-2d';
import { Labels } from './components/labels';
import { Toolbar } from './components/toolbar';
import { cn, Message, Path, PathData, PathNode } from '@/lib/utils';

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

export default function Home() {

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
  const desktopChartRef = useRef<ForceGraphMethods<Node, LinkType>>()
  const mobileChartRef = useRef<ForceGraphMethods<Node, LinkType>>()
  const [menuOpen, setMenuOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [searchNode, setSearchNode] = useState<PathNode>({});
  const [cooldownTicks, setCooldownTicks] = useState<number | undefined>(0)
  const [cooldownTime, setCooldownTime] = useState<number>(0)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([]);
  const [query, setQuery] = useState('');
  const [selectedPath, setSelectedPath] = useState<PathData>();
  const [paths, setPaths] = useState<PathData[]>([]);
  const chatPanel = useRef<ImperativePanelHandle>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [carouselApi, setCarouselApi] = useState<CarouselApi>()

  useEffect(() => {
    if (path?.start?.id && path?.end?.id) {
      console.log(path?.start?.id, path?.end?.id)
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

    const result = await fetch(`/api/repo/?url=${prepareArg(createURL)}`, {
      method: 'POST',
    })

    if (!result.ok) {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: await result.text(),
      })
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

    setGraph(Graph.empty())

    const result = await fetch(`/api/repo/${prepareArg(graphName)}`, {
      method: 'GET'
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
    const g = Graph.create(json.result.entities, graphName)
    setGraph(g)
    setIsPathResponse(false)
    chatPanel.current?.expand()
    // @ts-ignore
    window.graph = g
  }

  // Send the user query to the server to expand a node
  async function onFetchNode(nodeIds: number[]) {

    const result = await fetch(`/api/repo/${prepareArg(graph.Id)}/neighbors`, {
      method: 'POST',
      body: JSON.stringify({ nodeIds }),
      headers: {
        'Content-Type': 'application/json'
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

    return graph.extend(json.result.neighbors, true)
  }

  const handleSearchSubmit = (node: any, chartRef: MutableRefObject<ForceGraphMethods<Node, LinkType> | undefined>) => {
    const chart = chartRef.current

    if (chart) {

      let chartNode = graph.Elements.nodes.find(n => n.id == node.id)

      if (!chartNode?.visible) {
        if (!chartNode) {
          chartNode = graph.extend({ nodes: [node], edges: [] }).nodes[0]
        } else {
          chartNode.visible = true
          setCooldownTicks(undefined)
          setCooldownTime(1000)
        }
        graph.visibleLinks(true, [chartNode!.id])
        setData({ ...graph.Elements })
      }

      setSearchNode(chartNode)
      setTimeout(() => {
        chart.zoomToFit(1000, 150, (n: NodeObject<Node>) => n.id === chartNode!.id);
      }, 0)
      setOptionsOpen(false)
    }
  }

  function onCategoryClick(name: string, show: boolean) {
    graph.Categories.find(c => c.name === name)!.show = show

    graph.Elements.nodes.forEach(node => {
      if (!(node.category === name)) return
      node.visible = show
    })

    graph.visibleLinks(show)

    setData({ ...graph.Elements })
  }

  const handleDownloadImage = async () => {
    try {
      const canvases = document.querySelectorAll('.force-graph-container canvas') as NodeListOf<HTMLCanvasElement>;
      if (!canvases) {
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
    <main className="h-[100dvh]">
      <div className='md:flex md:flex-col hidden h-screen'>
        <header className="flex flex-col text-xl">
          <div className="flex items-center justify-between py-4 px-8">
            <div className="flex gap-4 items-center">
              <Link href="https://www.falkordb.com" target='_blank'>
                <Image src="/logo_02.svg" alt="FalkorDB" width={27.73} height={23.95} />
              </Link>
              <h1 className='font-bold text-[22px]'>
                CODE GRAPH
              </h1>
            </div>
            <ul className="flex gap-4 items-center font-medium">
              <Link title="Home" className="flex gap-2.5 items-center p-4" href="https://www.falkordb.com" target='_blank'>
                <HomeIcon />
                <p>Main Website</p>
              </Link>
              <Link title="Github" className="flex gap-2.5 items-center p-4" href="https://github.com/FalkorDB/code-graph" target='_blank'>
                <Github />
                <p>Github</p>
              </Link>
              <Link title="Discord" className="flex gap-2.5 items-center p-4" href="https://discord.gg/falkordb" target='_blank'>
                <BoomBox />
                <p>Discord</p>
              </Link>
              <DropdownMenu open={tipOpen} onOpenChange={setTipOpen}>
                <DropdownMenuTrigger asChild>
                  <button title="Tip" className="flex gap-2.5 items-center p-4">
                    <BookOpen />
                    <p>Tip</p>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className='flex-col flex p-4 gap-6 max-w-[30dvw]'>
                  <div className='flex justify-between items-center'>
                    <DropdownMenuLabel className='font-oswald text-[20px] font-semibold leading-[20px] text-left'>HOW TO USE THE PRODUCT</DropdownMenuLabel>
                    <button
                      title='Close'
                      onClick={() => setTipOpen(false)}
                    >
                      <X />
                    </button>
                  </div>
                  {
                    DESKTOP_TIPS.map((tip, index) => (
                      <div key={index} className='flex flex-col gap-4 text-[#7D7D7D]'>
                        <div className='flex gap-3 items-center'>
                          <h1 className='text-black font-bold'>{tip.title}</h1>
                          <p className='bg-[#ECECEC] p-1 rounded italic'>{tip.keyboardCommand}</p>
                        </div>
                        <p>{tip.description}</p>
                      </div>
                    ))
                  }
                </DropdownMenuContent>
              </DropdownMenu>
              {/* <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
              <button
              className="h-full bg-black p-4 text-white rounded-lg"
              title="Create new project"
              >
              <p>Create new project</p>
              </button>
              </DialogTrigger>
              <DialogContent className='max-w-[26%] gap-8'>
              <DialogHeader>
              <DialogTitle>{!isSubmit ? "CREATE A NEW PROJECT" : "THANK YOU FOR A NEW REQUEST"}</DialogTitle>
              </DialogHeader>
              <DialogDescription className='text-warp'>
              {
                !isSubmit
                ? "Please provide the URL of the model to connect and start querying data"
                : "Processing your graph, this could take a while. We appreciate your patience"
                }
                </DialogDescription>
                {
                  !isSubmit ?
                  <form className='flex flex-col gap-4' onSubmit={onCreateRepo}>
                  <input
                  className='border p-3 rounded-lg'
                  type="text"
                  value={createURL}
                  onChange={(e) => setCreateURL(e.target.value)}
                  placeholder="Type URL"
                  />
                  <div className='flex flex-row-reverse'>
                  <button
                  className='bg-black p-3 text-white rounded-lg'
                  type='submit'
                  title='Create Project'
                  >
                  <p>Create</p>
                  </button>
                  </div>
                  </form>
                  : <Progress value={0} />
                  }
                  </DialogContent>
                  </Dialog> */}
            </ul>
          </div>
          <div className='h-2.5 bg-gradient-to-r from-[#EC806C] via-[#B66EBD] to-[#7568F2]' />
        </header>
        <PanelGroup direction="horizontal" className="w-full h-full">
          <Panel
            defaultSize={graph.Id ? 70 : 100}
            maxSize={100}
            minSize={50}
          >
            <CodeGraph
              graph={graph}
              data={data}
              setData={setData}
              chartRef={desktopChartRef}
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
              cooldownTicks={cooldownTicks}
              setCooldownTicks={setCooldownTicks}
              cooldownTime={cooldownTime}
              setCooldownTime={setCooldownTime}
              onCategoryClick={onCategoryClick}
              handleDownloadImage={handleDownloadImage}
            />
          </Panel>
          <PanelResizeHandle className={cn(!graph.Id && 'hidden')} />
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
              chartRef={desktopChartRef}
              setPath={setPath}
              path={path}
              repo={graph.Id}
              graph={graph}
              selectedPathId={selectedPathId}
              isPathResponse={isPathResponse}
              setIsPathResponse={setIsPathResponse}
              setData={setData}
              paths={paths}
              setPaths={setPaths}
            />
          </Panel>
        </PanelGroup>
      </div>
      <div className='flex flex-col md:hidden h-full overflow-hidden'>
        <header className='flex justify-center items-center relative bg-gray-100'>
          <Link href="https://www.falkordb.com" target='_blank'>
            <Image priority style={{ width: 'auto', height: '70px', background: "transparent" }} src="/code-graph-logo.svg" alt="FalkorDB" width={0} height={0} />
          </Link>
          <button className='absolute top-6 right-4' onClick={() => setMenuOpen(prev => !prev)}>
            <AlignRight />
          </button>
        </header>

        {menuOpen && (
          <div className='absolute bottom-0 top-[70px] left-0 right-0 z-20 bg-white shadow-lg'>
            <ul className='h-full flex flex-col gap-16 p-8 items-center'>
              <li>
                <Link href="https://github.com/FalkorDB/code-graph" target='_blank'>
                  <p>Github</p>
                </Link>
              </li>
              <li>
                <Link href="https://discord.gg/falkordb" target='_blank'>
                  <p>Discord</p>
                </Link>
              </li>
              <li>
                <Link href="https://www.falkordb.com" target='_blank'>
                  <p>Main Website</p>
                </Link>
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
                        "h-2 w-2 rounded-full bg-gray-300",
                        index === activeIndex && "bg-gray-600"
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
        <div className='flex flex-col grow'>
          <CodeGraph
            graph={graph}
            data={data}
            setData={setData}
            chartRef={mobileChartRef}
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
            cooldownTicks={cooldownTicks}
            setCooldownTicks={setCooldownTicks}
            cooldownTime={cooldownTime}
            setCooldownTime={setCooldownTime}
            onCategoryClick={onCategoryClick}
            handleDownloadImage={handleDownloadImage}
          />
          {graph.Id && (
            <div className='flex items-center p-4 gap-4'>
              <Drawer open={chatOpen} onOpenChange={setChatOpen}>
                <DrawerTrigger asChild>
                  <button className='grow bg-blue text-white p-2 rounded-md'>
                    <p>Chat</p>
                  </button>
                </DrawerTrigger>
                <DrawerContent handleClassName='bg-gray-500 h-1' className='md:hidden flex flex-col h-[80dvh]'>
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
                    chartRef={mobileChartRef}
                    setPath={setPath}
                    path={path}
                    repo={graph.Id}
                    graph={graph}
                    selectedPathId={selectedPathId}
                    isPathResponse={isPathResponse}
                    setIsPathResponse={setIsPathResponse}
                    setData={setData}
                    setChatOpen={setChatOpen}
                    paths={paths}
                    setPaths={setPaths}
                  />
                </DrawerContent>
              </Drawer>
              <Drawer open={optionsOpen} onOpenChange={setOptionsOpen}>
                <DrawerTrigger asChild>
                  <button className='grow border border-blue text-blue p-2 rounded-md'>
                    <p>Options</p>
                  </button>
                </DrawerTrigger>
                <DrawerContent handleClassName='mt-0 bg-gray-500 h-1' overlayClassName='bg-transparent' className='md:hidden flex flex-col gap-8 p-4 items-center bg-gray-300 border-2 border-gray-500'>
                  <VisuallyHidden>
                    <DrawerTitle />
                    <DrawerDescription />
                  </VisuallyHidden>
                  <Toolbar
                    className='bg-transparent absolute -top-14 left-0 w-full justify-between px-6'
                    chartRef={mobileChartRef}
                  />
                  <Input
                    className='border-2 border-gray-500'
                    graph={graph}
                    onValueChange={(node) => setSearchNode(node)}
                    icon={<Search />}
                    handleSubmit={(node) => handleSearchSubmit(node, mobileChartRef)}
                    node={searchNode}
                  />
                  <Labels categories={graph.Categories} onClick={onCategoryClick} />
                  <div className='flex flex-col gap-2 items-center'>
                    <button
                      className='control-button'
                      onClick={handleDownloadImage}
                    >
                      <Download size={30} />
                    </button>
                    <p className=''>Take Screenshot</p>
                  </div>
                </DrawerContent>
              </Drawer>
            </div>
          )}
        </div>
      </div>
    </main >
  )
}
