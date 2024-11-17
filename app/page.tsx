'use client'

import { useEffect, useRef, useState } from 'react';
import { Chat } from './components/chat';
import { Graph, Node } from './components/model';
import { BookOpen, Github, HomeIcon, X } from 'lucide-react';
import Link from 'next/link';
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { CodeGraph } from './components/code-graph';
import { toast } from '@/components/ui/use-toast';
import { GraphContext } from './components/provider';
import Image from 'next/image';
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

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
    title: "Zoom In",
    description: "Use this command to zoom into the graph.",
    keyboardCommand: "Ctrl + Plus"
  },
  {
    title: "Zoom Out",
    description: "Use this command to zoom out of the graph.",
    keyboardCommand: "Ctrl + Minus"
  },
  {
    title: "Pan",
    description: "Click and drag to pan around the graph.",
    keyboardCommand: "Mouse Drag"
  },
  {
    title: "Select Node",
    description: "Click on a node to select it.",
    keyboardCommand: "Mouse Click"
  },
  {
    title: "Expand Node",
    description: "Use this command to expand node.",
    keyboardCommand: "Mouse Double Click"
  }
]

export default function Home() {

  const [graph, setGraph] = useState(Graph.empty());
  const [selectedValue, setSelectedValue] = useState("");
  const [selectedPathId, setSelectedPathId] = useState<string>();
  const [isPathResponse, setIsPathResponse] = useState<boolean>(false);
  const [createURL, setCreateURL] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [tipOpen, setTipOpen] = useState(false)
  const [options, setOptions] = useState<string[]>([]);
  const [path, setPath] = useState<Path | undefined>();
  const [isSubmit, setIsSubmit] = useState<boolean>(false);
  const chartRef = useRef<cytoscape.Core | null>(null)

  useEffect(() => {
    const run = async () => {
      const result = await fetch(`/api/repo`, {
        method: 'GET',
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
      setOptions(json.result)
    }

    run()
  }, [])

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

    const result = await fetch(`/api/repo/?url=${createURL}`, {
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

    const result = await fetch(`/api/repo/${graphName}`, {
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
    setGraph(Graph.create(json.result.entities, graphName))
  }

  // Send the user query to the server to expand a node
  async function onFetchNode(node: Node) {
    const result = await fetch(`/api/repo/${graph.Id}/${node.id}`, {
      method: 'GET'
    })

    if (!result.ok) {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: await result.text(),
      })
      return []
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
              <DropdownMenuContent className='flex-col flex p-4 gap-6'>
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
                        <p className='bg-[#ECECEC] p-1 rounded'>{tip.keyboardCommand}</p>
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
              chartRef={chartRef}
              options={options}
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
            chartRef={chartRef}
            setPath={setPath}
            path={path}
            repo={graph.Id}
            graph={graph}
            selectedPathId={selectedPathId}
            isPath={isPathResponse}
            setIsPath={setIsPathResponse}
          />
        </Panel>
      </PanelGroup>
    </main>
  )
}
