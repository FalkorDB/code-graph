'use client'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import ReactECharts, { EChartsInstance } from 'echarts-for-react';
import { useState, useRef } from 'react';
import { Chat } from './chat';
import { Graph } from './model';
import { Github, HomeIcon, ZoomIn, ZoomOut } from 'lucide-react';
import { toast } from '@/components/ui/use-toast';
import Link from 'next/link';
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

export default function Home() {

  const [url, setURL] = useState('https://github.com/falkorDB/falkordb-py');
  const [graph, setGraph] = useState<Graph>( Graph.empty());

  const echartRef = useRef<EChartsInstance | null>(null)
  const factor = useRef<number>(1)

  function getOptions(graph: Graph) {
    const currentFactor = factor.current
    return {
      name: graph.Id,
      tooltip: {
        position: 'right',
      },
      legend: [
        {
          data: graph.Categories.map(function (c) {
            return c.name;
          })
        }
      ],
      toolbox: {
        show: true,
        feature: {
          // Shows zoom in and zoom out custom buttons
          myZoomIn: {
            show: true,
            title: 'Zoom In',
            icon: 'path://M19 11 C19 15.41 15.41 19 11 19 6.58 19 3 15.41 3 11 3 6.58 6.58 3 11 3 15.41 3 19 6.58 19 11 zM21 21 C19.55 19.55 18.09 18.09 16.64 16.64 M11 8 C11 10 11 12 11 14 M8 11 C10 11 12 11 14 11',
            onclick: function () {
              handleZoomClick(1.1)
            }
          },
          myZoomOut: {
            show: true,
            title: 'Zoom Out',
            icon: 'path://M19 11 C19 15.41 15.41 19 11 19 6.58 19 3 15.41 3 11 3 6.58 6.58 3 11 3 15.41 3 19 6.58 19 11 zM21 21 C19.55 19.55 18.09 18.09 16.64 16.64 M8 11 C10 11 12 11 14 11',
            onclick: function () {
              handleZoomClick(0.9)
            }
          },
          restore: {},
          saveAsImage: {},
        }
      },
      series: [{
        type: 'graph',
        layout: 'force',
        animation: false,
        label: {
          show: true,
          position: 'inside',
          fontSize: 2 * currentFactor
        },
        symbolSize: 10,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 0.8 * currentFactor,
        draggable: true,
        nodes: graph.Nodes,
        edges: graph.Edges,
        categories: graph.Categories,
        force: {
          repulsion: 100,
        },
        edgeLabel: {
          fontSize: 2 * currentFactor
        },
        roam: true,
        autoCurveness: true,
        lineStyle: {
          width: 0.3 * currentFactor,
          opacity: 0.7
        },
        zoom: currentFactor
      }]
    }
  }

  // A function that handles the change event of the url input box
  async function handleRepoInputChange(event: any) {

    if (event.key === "Enter") {
      await handleSubmit(event);
    }

    // Get the new value of the input box
    const value = event.target.value;

    // Update the url state
    setURL(value);
  }

  // A function that handles the click event
  async function handleSubmit(event: any) {
    event.preventDefault();

    fetch('/api/repo', {
      method: 'POST',
      body: JSON.stringify({
        url: url
      })
    }).then(response => response.json())
      .then(data => {
        let graph = Graph.create(data)
        setGraph(graph)
      })
      .catch((error) => {
        toast({
          variant: "destructive",
          title: "Uh oh! Something went wrong.",
          description: error.message,
        })
      })
  }
  function handleZoomClick(changefactor: number) {
    factor.current *= changefactor
    let chart = echartRef.current
    if (chart) {
      let options = getOptions(graph)
      chart.setOption(options)
    }
  }

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
          <header className="border p-4">
            <form className="flex flex-row gap-2" onSubmit={handleSubmit}>
              <Input placeholder="Github repo URL" className='border' type="url" onChange={handleRepoInputChange} />
              <Button type="submit" >Send</Button>
            </form>
          </header>
          <main className="h-full">
            <ReactECharts
              option={getOptions(graph)}
              style={{ height: '100%', width: '100%' }}
              onChartReady={(e) => {
                echartRef.current = e
              }}
              onEvents={{
                graphRoam: (params: any) => {
                  if (params.zoom) {
                    handleZoomClick(params.zoom)
                  }
                },
                dblclick: async (params: any) => {

                  let value = params?.data?.value;
                  if (!value) {
                    return
                  }
                  let node = JSON.parse(value)

                  fetch(`/api/repo/${graph.Id}/${node.name}`, {
                    method: 'GET'
                  })
                    .then(response => response.json())
                    .then(data => {
                      graph.extend(data)
                      setGraph(graph)
                    })
                    .catch((error) => {
                      toast({
                        variant: "destructive",
                        title: "Uh oh! Something went wrong.",
                        description: error.message,
                      })
                    })
                }
              }}
            />
          </main>
        </Panel>
        <PanelResizeHandle  className="w-1 bg-gray-500"/>
        <Panel className="flex flex-col border" defaultSize={25} collapsible={true} minSize={10}>
          <Chat repo={graph.Id} />
        </Panel>
      </PanelGroup>
    </main>
  )
}
