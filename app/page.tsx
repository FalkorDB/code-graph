'use client'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import ReactECharts from 'echarts-for-react';
import { useState } from 'react';
import { Chat } from './chat';
import { Graph, SAMPLE_GRAPH } from './api/model';

export default function Home() {

  const [url, setURL] = useState('');
  const [graph, setGraph] = useState<Graph>(SAMPLE_GRAPH);

  const option = {
    tooltip: {
      position: 'right',
    },
    legend: [
      {
        data: graph.categories.map(function (c) {
          return c.name;
        })
      }
    ],
    toolbox: {
      show: true,
      feature: {
        restore: {},
        saveAsImage: {}
      }
    },
    series: [{
      type: 'graph',
      layout: 'force',
      animation: false,
      label: {
        normal: {
          position: 'right',
          formatter: '{b}'
        }
      },
      draggable: true,
      data: graph.nodes.map(function (node:any, idx) {
        node.id = idx;
        return node;
      }),
      categories: graph.categories,
      force: {
        // initLayout: 'circular'
        // repulsion: 20,
        edgeLength: 5,
        repulsion: 20,
        gravity: 0.2
      },
      edges: graph.edges,
      emphasis: {
        focus: 'adjacency',
        label: {
          position: 'right',
          show: true
        }
      },
      roam: true,
      lineStyle: {
        color: 'source',
        width: 3.0,
        curveness: 0.1,
        opacity: 0.7
      },
    }]
  };

  // A function that handles the change event of the url input box
  async function handleRepoInputChange(event: any) {

    if (event.key === "Enter") {
      await handleRepoClick(event);
    }

    // Get the new value of the input box
    const value = event.target.value;

    // Update the url state
    setURL(value);
  }

  // A function that handles the click event
  async function handleRepoClick(event: any) {
    fetch('/api/repo', {
      method: 'POST',
      body: JSON.stringify({
        url: url
      })
    }).then(response => response.json())
      .then(data => {
        console.log(data)
        setGraph(data)
      })
      .catch((error) => {
        console.error('Error:', error);
      })
  }

  return (
    <main className="h-screen p-8">
      <div className="w-full flex flex-row h-full">
        <section className="flex flex-col w-4/6 border">
          <header className="border p-4 flex flex-row gap-2">
            <Input placeholder="Github repo URL" className='border' type='url' onChange={handleRepoInputChange} />
            <Button onClick={handleRepoClick}>Send</Button>
          </header>
          <main className="h-full">
            <ReactECharts
              option={option}
              style={{ height: '100%', width: '100%' }}
            />
          </main>
        </section>
        <aside className="flex flex-col w-2/6 border">
          <Chat />
        </aside>
      </div>
    </main>
  )
}
