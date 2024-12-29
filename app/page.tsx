'use client'

import { useEffect, useRef, useState } from 'react';
import { Chat } from './components/chat';
import { Graph, GraphData } from './components/model';
import { BookOpen, Github, HomeIcon, X } from 'lucide-react';
import Link from 'next/link';
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { CodeGraph } from './components/code-graph';
import { toast } from '@/components/ui/use-toast';
import { GraphContext } from './components/provider';
import Image from 'next/image';
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { prepareArg } from './utils';

export type PathNode = {
  id?: number
  name?: string
}

export type Path = {
  start?: PathNode,
  end?: PathNode
}

type Tip = {
  title: string
  description: string
  keyboardCommand: string
}

const TIPS: Tip[] = [
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
  const chartRef = useRef<any>()

  useEffect(() => {
    setIsPathResponse(false)
  }, [graph.Id])

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

  return (
    <main className="h-screen flex flex-col">
      <header className="flex flex-col text-xl">
        <div className="flex items-center justify-between py-4 px-8">
          <div className="flex gap-4 items-center">
            <Link href="https://www.falkordb.com" target='_blank'>
              <Image src="/logo_02.svg" alt="FalkorDB" width={27.73} height={23.95} />
            </Link>
            <h1 className='italic font-bold text-[22px]'>
              CODE GRAPH
            </h1>
          </div>
          <ul className="flex gap-4 items-center font-medium">
            <Link title="Home" className="flex gap-2.5 items-center p-4" href="https://www.falkordb.com" target='_blank'>
              <HomeIcon />
              <p>Home</p>
            </Link>
            <Link title="Github" className="flex gap-2.5 items-center p-4" href="https://github.com/FalkorDB/code-graph" target='_blank'>
              <Github />
              <p>Github</p>
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
                  TIPS.map((tip, index) => (
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
        <Panel defaultSize={70} className="flex flex-col" minSize={50}>
          <GraphContext.Provider value={graph}>
            <CodeGraph
              data={data}
              setData={setData}
              chartRef={chartRef}
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
            />
          </GraphContext.Provider>
        </Panel>
        <PanelResizeHandle />
        <Panel className="border-l min-w-[420px]" defaultSize={30} >
          <Chat
            setPath={setPath}
            path={path}
            repo={graph.Id}
            graph={graph}
            selectedPathId={selectedPathId}
            isPathResponse={isPathResponse}
            setIsPathResponse={setIsPathResponse}
            setData={setData}
          />
        </Panel>
      </PanelGroup>
    </main>
  )
}
