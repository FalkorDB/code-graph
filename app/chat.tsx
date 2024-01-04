import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useEffect, useState } from "react";


enum MessageTypes {
    Query,
    Response,
}

interface Message {
    text: string;
    type: MessageTypes;
}

export function Chat() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [query, setQuery] = useState('');


    // A function that handles the change event of the url input box
    async function handleQueryInputChange(event: any) {

        if (event.key === "Enter") {
            await handleQueryClick(event);
        }

        // Get the new value of the input box
        const value = event.target.value;

        // Update the url state
        setQuery(value);
    }

    // A function that handles the click event
    async function handleQueryClick(event: any) {

        setMessages((messages) => [...messages, { text: query, type: MessageTypes.Query }]);

        fetch(`/api/repo/repo1?q=${query}&type=text`, {
            method: 'GET'
        })
            .then(response => response.json())
            .then(data => {
                setMessages((messages) => [...messages, { text: data.result, type: MessageTypes.Response }]);
            })
            .catch((error) => {
                console.error('Error:', error);
            })
    }

    // useEffect(() => {
    //     const socket = io();
    //     socket.on("message", (message: Message) => {
    //         setMessages((messages) => [...messages, message]);
    //     });
    // }, []);

    return (
        <>
            <main className="border p-4 flex-1 space-y-4">
                {
                    messages.map((message, index) => {
                        if (message.type === MessageTypes.Query) {
                            return (<div key={index} className="flex items-end gap-2">
                                <div className="rounded-lg bg-zinc-200 dark:bg-zinc-700 p-2">
                                    <p className="text-sm">{message.text}</p>
                                </div>
                            </div>)
                        } else {
                            return (<div key={index} className="flex items-end gap-2 justify-end">
                                <div className="rounded-lg bg-blue-500 text-white p-2">
                                    <p className="text-sm">{message.text}</p>
                                </div>
                            </div>)
                        }
                    })
                }
                {/* <div className="space-y-4">
                    <div className="flex items-end gap-2">
                        <div className="rounded-lg bg-zinc-200 dark:bg-zinc-700 p-2">
                            <p className="text-sm">Hello, how are you?</p>
                        </div>
                    </div>
                    <div className="flex items-end gap-2 justify-end">
                        <div className="rounded-lg bg-blue-500 text-white p-2">
                            <p className="text-sm">Im fine, thanks for asking!</p>
                        </div>
                    </div>
                </div> */}
            </main>
            <footer className="border p-4 flex flex-row gap-2">
                <Input className="" placeholder="Type a query..." onChange={handleQueryInputChange} />
                <Button onClick={handleQueryClick}>Send</Button>
            </footer>
        </>
    );
}
