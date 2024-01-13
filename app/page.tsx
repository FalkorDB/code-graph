'use client'

import { useState } from 'react';
import { Chat } from './components/chat';
import { Graph, Node } from './components/model';
import { Github, HomeIcon } from 'lucide-react';
import Link from 'next/link';
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { CodeGraph } from './components/code-graph';
import { toast } from '@/components/ui/use-toast';

export default function Home() {

  const [graph, setGraph] = useState(Graph.empty());

  function onFetchGraph(url: string) {
    let value = url;
    if (!value || value.length === 0) {
      value = 'https://github.com/falkorDB/falkordb-py';
    }

    // Send the user query to the server to fetch a repo graph
    fetch('/api/repo', {
      method: 'POST',
      body: JSON.stringify({
        url: value
      })
    }).then(async (result) => {
      if (result.status >= 300) {
        throw Error(await result.text())
      }
      return result.json()
    }).then(data => {
      let graph = Graph.create(data);
      setGraph(graph);
    }).catch((error) => {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: error.message,
      });
    });
  }

  // Send the user query to the server to expand a node
  function onFetchNode(node: Node) {
    fetch(`/api/repo/${graph.Id}/${node.name}`, {
      method: 'GET'
    }).then(async (result) => {
      if (result.status >= 300) {
        throw Error(await result.text())
      }
      return result.json()
    }).then(data => {
      graph.extend(data)
      setGraph(graph)
    }).catch((error) => {
      toast({
        variant: "destructive",
        title: "Uh oh! Something went wrong.",
        description: error.message,
      })
    })
  }

  return (
    <main className="h-screen flex flex-col">
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
          <CodeGraph graph={graph} onFetchGraph={onFetchGraph} onFetchNode={onFetchNode} />
        </Panel>
        <PanelResizeHandle className="w-1 bg-gray-500" />
        <Panel className="flex flex-col border" defaultSize={25} collapsible={true} minSize={10}>
          <Chat repo={graph.Id} />
        </Panel>
      </PanelGroup>
    </main>
  )
}
