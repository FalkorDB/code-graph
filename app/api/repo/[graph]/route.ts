import { NextRequest, NextResponse } from "next/server"

export async function GET(request: NextRequest, { params }: { params: { graph: string } }) {

    const graphName = params.graph

    try {
        const result = await fetch(`${process.env.BACKEND_URL}/graph_entities?repo=${graphName}`, {
            method: 'GET',
            headers: {
                "Authorization": process.env.SECRET_TOKEN!,
            }
        })

        if (!result.ok) {
            throw new Error(await result.text())
        }

        const json = await result.json()

        return NextResponse.json({ result: json }, { status: 200 })
    } catch (err) {
        return NextResponse.json({ message: (err as Error).message }, { status: 400 })
    }
}

export async function POST(request: NextRequest, { params }: { params: { graph: string } }) {

    const type = request.nextUrl.searchParams.get('type') || "count"
    const graphName = params.graph

    try {
        switch (type) {
            // case "commit": {
            //     const result = await fetch(`${process.env.BEAKEND_URL}/list_commits`, {
            //         method: 'POST',
            //         body: JSON.stringify({ repo: graphName }),
            //         headers: {
            //             "Authorization": process.env.SECRET_TOKEN!,
            //             "Content-Type": 'application/json'
            //         }
            //     })

            //     if (!result.ok) {
            //         throw new Error(await result.text())
            //     }

            //     const json = await result.json()

            //     return NextResponse.json({ result: json }, { status: 200 })
            // }
            // case "switchCommit": {
            //     return NextResponse.json({
            //         result: {
            //             deletions: {
            //                 'nodes': [
            //                     {
            //                         "alias": "",
            //                         "id": 2,
            //                         "labels": [
            //                             "Function"
            //                         ],
            //                         "properties": {
            //                             "args": [
            //                                 [
            //                                     "cls",
            //                                     "Unknown"
            //                                 ]
            //                             ],
            //                             "name": "setUpClass",
            //                             "path": "tests/test_kg_gemini.py",
            //                             "src": "def setUpClass(cls):\n\n        cls.ontology = Ontology([], [])\n\n        cls.ontology.add_entity(\n            Entity(\n                label=\"Actor\",\n                attributes=[\n                    Attribute(\n                        name=\"name\",\n                        attr_type=AttributeType.STRING,\n                        unique=True,\n                        required=True,\n                    ),\n                ],\n            )\n        )\n        cls.ontology.add_entity(\n            Entity(\n                label=\"Movie\",\n                attributes=[\n                    Attribute(\n                        name=\"title\",\n                        attr_type=AttributeType.STRING,\n                        unique=True,\n                        required=True,\n                    ),\n                ],\n            )\n        )\n        cls.ontology.add_relation(\n            Relation(\n                label=\"ACTED_IN\",\n                source=\"Actor\",\n                target=\"Movie\",\n                attributes=[\n                    Attribute(\n                        name=\"role\",\n                        attr_type=AttributeType.STRING,\n                        unique=False,\n                        required=False,\n                    ),\n                ],\n            )\n        )\n\n        cls.graph_name = \"IMDB_gemini\"\n\n        model = GeminiGenerativeModel(model_name=\"gemini-1.5-flash-001\")\n        cls.kg = KnowledgeGraph(\n            name=cls.graph_name,\n            ontology=cls.ontology,\n            model_config=KnowledgeGraphModelConfig.with_model(model),\n        )",
            //                             "src_end": 82,
            //                             "src_start": 29
            //                         }
            //                     },
            //                     {
            //                         "alias": "",
            //                         "id": 13,
            //                         "labels": [
            //                             "Function"
            //                         ],
            //                         "properties": {
            //                             "args": [
            //                                 [
            //                                     "self",
            //                                     "Unknown"
            //                                 ],
            //                                 [
            //                                     "restaurants_kg",
            //                                     "KnowledgeGraph"
            //                                 ],
            //                                 [
            //                                     "attractions_kg",
            //                                     "KnowledgeGraph"
            //                                 ]
            //                             ],
            //                             "name": "import_data",
            //                             "path": "tests/test_multi_agent.py",
            //                             "src": "def import_data(\n        self,\n        restaurants_kg: KnowledgeGraph,\n        attractions_kg: KnowledgeGraph,\n    ):\n        with open(\"tests/data/cities.json\") as f:\n            cities = loads(f.read())\n        with open(\"tests/data/restaurants.json\") as f:\n            restaurants = loads(f.read())\n        with open(\"tests/data/attractions.json\") as f:\n            attractions = loads(f.read())\n\n        for city in cities:\n            restaurants_kg.add_node(\n                \"City\",\n                {\n                    \"name\": city[\"name\"],\n                    \"weather\": city[\"weather\"],\n                    \"population\": city[\"population\"],\n                },\n            )\n            restaurants_kg.add_node(\"Country\", {\"name\": city[\"country\"]})\n            restaurants_kg.add_edge(\n                \"IN_COUNTRY\",\n                \"City\",\n                \"Country\",\n                {\"name\": city[\"name\"]},\n                {\"name\": city[\"country\"]},\n            )\n\n            attractions_kg.add_node(\n                \"City\",\n                {\n                    \"name\": city[\"name\"],\n                    \"weather\": city[\"weather\"],\n                    \"population\": city[\"population\"],\n                },\n            )\n            attractions_kg.add_node(\"Country\", {\"name\": city[\"country\"]})\n            attractions_kg.add_edge(\n                \"IN_COUNTRY\",\n                \"City\",\n                \"Country\",\n                {\"name\": city[\"name\"]},\n                {\"name\": city[\"country\"]},\n            )\n\n        for restaurant in restaurants:\n            restaurants_kg.add_node(\n                \"Restaurant\",\n                {\n                    \"name\": restaurant[\"name\"],\n                    \"description\": restaurant[\"description\"],\n                    \"rating\": restaurant[\"rating\"],\n                    \"food_type\": restaurant[\"food_type\"],\n                },\n            )\n            restaurants_kg.add_edge(\n                \"IN_CITY\",\n                \"Restaurant\",\n                \"City\",\n                {\"name\": restaurant[\"name\"]},\n                {\"name\": restaurant[\"city\"]},\n            )\n\n        for attraction in attractions:\n            attractions_kg.add_node(\n                \"Attraction\",\n                {\n                    \"name\": attraction[\"name\"],\n                    \"description\": attraction[\"description\"],\n                    \"type\": attraction[\"type\"],\n                },\n            )\n            attractions_kg.add_edge(\n                \"IN_CITY\",\n                \"Attraction\",\n                \"City\",\n                {\"name\": attraction[\"name\"]},\n                {\"name\": attraction[\"city\"]},\n            )",
            //                             "src_end": 310,
            //                             "src_start": 230
            //                         }
            //                     },
            //                 ],
            //                 'edges': [
            //                     {
            //                         "alias": "",
            //                         "dest_node": 13,
            //                         "id": 460,
            //                         "properties": {},
            //                         "relation": "CALLS",
            //                         "src_node": 2
            //                     },
            //                 ]
            //             },
            //             additions: {
            //                 'nodes': [
            //                     {
            //                         "alias": "",
            //                         "id": 13,
            //                         "labels": [
            //                             "File"
            //                         ],
            //                         "properties": {
            //                             "ext": ".py",
            //                             "name": "test_kg_gemini.py",
            //                             "path": "tests"
            //                         }
            //                     },
            //                     {
            //                         "alias": "",
            //                         "id": 2,
            //                         "labels": [
            //                             "Class"
            //                         ],
            //                         "properties": {
            //                             "doc": "\"\"\"\n    Test Knowledge Graph\n    \"\"\"",
            //                             "name": "TestKGGemini",
            //                             "path": "tests/test_kg_gemini.py",
            //                             "src_end": 106,
            //                             "src_start": 23
            //                         }
            //                     },
            //                 ],
            //                 'edges': [
            //                     {
            //                         "alias": "",
            //                         "dest_node": 13,
            //                         "id": 460,
            //                         "properties": {},
            //                         "relation": "DEFINES",
            //                         "src_node": 2
            //                     },
            //                 ],
            //             },
            //             modifications: {
            //                 'nodes': [
            //                     {
            //                         "alias": "",
            //                         "id": 3,
            //                         "labels": [
            //                             "Function"
            //                         ],
            //                         "properties": {
            //                             "args": [
            //                                 []
            //                             ],
            //                             "name": "",
            //                             "path": "",
            //                             "src": "",                                        
            //                             "src_end": 0,
            //                             "src_start": 0
            //                         }
            //                     },
            //                     {
            //                         "alias": "",
            //                         "id": 61,
            //                         "labels": [
            //                             "Function"
            //                         ],
            //                         "properties": {
            //                             "args": [
            //                                 [],
            //                                 []
            //                             ],
            //                             "doc": "",
            //                             "name": "",
            //                             "path": "",
            //                             "ret_type": "",
            //                             "src": "",
            //                             "src_end": 0,
            //                             "src_start": 0
            //                         }
            //                     },
            //                 ],
            //                 'edges': [
            //                     {
            //                         "alias": "",
            //                         "dest_node": 61,
            //                         "id": 439,
            //                         "properties": {
            //                             name: "Source"
            //                         },
            //                         "relation": "CALLS",
            //                         "src_node": 3
            //                     },
            //                 ]
            //             }
            //         }
            //     }, { status: 200 })
            // }
            case "autoComplete": {
                const prefix = request.nextUrl.searchParams.get('prefix')!
                const result = await fetch(`${process.env.BACKEND_URL}/auto_complete`, {
                    method: 'POST',
                    body: JSON.stringify({ repo: graphName, prefix }),
                    headers: {
                        "Authorization": process.env.SECRET_TOKEN!,
                        "Content-Type": 'application/json'
                    }
                })

                if (!result.ok) {
                    throw new Error(await result.text())
                }

                const json = await result.json()

                return NextResponse.json({ result: json }, { status: 200 })
            }
            default: {
                const result = await fetch(`${process.env.BACKEND_URL}/repo_info`, {
                    method: 'POST',
                    body: JSON.stringify({ repo: graphName }),
                    headers: {
                        "Authorization": process.env.SECRET_TOKEN!,
                        "Content-Type": 'application/json'
                    }
                })

                if (!result.ok) {
                    throw new Error(await result.text())
                }

                const json = await result.json()

                return NextResponse.json({ result: json }, { status: 200 })
            }
        }
    } catch (err) {
        return NextResponse.json({ message: (err as Error).message }, { status: 400 })
    }


}