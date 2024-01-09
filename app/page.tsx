'use client'

import { useState, createContext } from 'react';
import { Chat } from './components/chat';
import { Graph } from './components/model';
import { Github, HomeIcon } from 'lucide-react';
import Link from 'next/link';
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { CodeGraph } from './components/code-graph';

export default function Home() {

  const [graph, setGraph] = useState(Graph.empty());

  return (
    <main className="h-screen p-8">
      <header className="flex items-center justify-between p-4 border">
        <Link href="https://www.falkordb.com" target='_blank'>
          <HomeIcon className="h-6 w-6" />
        </Link>
        <h1 className='font-extrabold'>
          Code Graph by <Link href="https://www.falkordb.com">FalkorDB</Link>
        </h1>
        <nav className="space-x-4">
          <Link className="text-gray-600 hover:text-gray-900" href="https://github.com/FalkorDB/code-graph" target='_blank'>
            <Github />
          </Link>
        </nav>
      </header>

      <PanelGroup direction="horizontal" className="w-full h-full">
        <Panel defaultSize={75} className="flex flex-col border" collapsible={true} minSize={30}>
          <CodeGraph graph={graph}  setGraph={setGraph}/>
        </Panel>
        <PanelResizeHandle className="w-1 bg-gray-500" />
        <Panel className="flex flex-col border" defaultSize={25} collapsible={true} minSize={10}>
          <Chat repo={graph.Id} />
        </Panel>
      </PanelGroup>
    </main>
  )
}
