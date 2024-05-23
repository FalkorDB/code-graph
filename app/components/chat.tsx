import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/use-toast";
import { useEffect, useRef, useState } from "react";
import { QUESTIONS } from "../api/repo/questions";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import Image from "next/image";

enum MessageTypes {
    Query,
    Response,
    Pending,
}

interface Message {
    text: string;
    type: MessageTypes;
}

export function Chat(props: { repo: string }) {

    // Holds the messages in the chat
    const [graphMessages, setGraphMessages] = useState<Message[]>([]);

    // Holds the messages in the chat
    const [vendorMessages, setVendorMessages] = useState<Message[]>([]);

    // Holds the user input while typing
    const [query, setQuery] = useState('');

    // A reference to the chat container to allow scrolling to the bottom
    const graphBottomRef: React.RefObject<HTMLDivElement> = useRef(null);
    
    const vendorBottomRef: React.RefObject<HTMLDivElement> = useRef(null);

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

    // Send the user query to the server
    async function sendQuery(q: string) {
        setGraphMessages((messages) => [...messages, { text: q, type: MessageTypes.Query }, { text: "", type: MessageTypes.Pending }]);
        setVendorMessages((messages) => [...messages, { text: q, type: MessageTypes.Query }, { text: "", type: MessageTypes.Pending }]);

        fetch(`/api/repo/${props.repo}?q=${encodeURIComponent(q)}&type=text`, {
            method: 'GET'
        }).then(async (result) => {
            if (result.status >= 300) {
                throw Error(await result.text())

            }

            return result.json()
        }).then(data => {
            // Create an array of messages from the current messages remove the last pending message and add the new response
            setGraphMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    messages = messages.slice(0, -1);
                }
                return [...messages, { text: data.result, type: MessageTypes.Response }];
            });
        }).catch((error) => {
            setGraphMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    return messages.slice(0, -1);
                }
                return messages
            });
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: error.message,
            });
        });

        fetch(`/api/repo/${props.repo}?q=${encodeURIComponent(q)}&type=text`, {
            method: 'GET'
        }).then(async (result) => {
            if (result.status >= 300) {
                throw Error(await result.text())

            }

            return result.json()
        }).then(data => {
            // Create an array of messages from the current messages remove the last pending message and add the new response
            setVendorMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    messages = messages.slice(0, -1);
                }
                return [...messages, { text: data.result, type: MessageTypes.Response }];
            });
        }).catch((error) => {
            setVendorMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    return messages.slice(0, -1);
                }
                return messages
            });
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: error.message,
            });
        });
    }

    // A function that handles the click event
    async function handleQueryClick(event: any) {
        event.preventDefault();
        return sendQuery(query);
    }

    // On question selected from the predefined questions list
    async function onQuestionSelected(value: string) {
        setQuery(value)
        return sendQuery(value)
    }

    // Scroll to the bottom of the chat on new message
    useEffect(() => {
        graphBottomRef.current?.scrollTo(0, graphBottomRef.current?.scrollHeight);
        vendorBottomRef.current?.scrollTo(0, vendorBottomRef.current?.scrollHeight);
    }, [graphMessages, vendorBottomRef]);

    return (
        <>
            <main className="h-full flex flex-row">
                <div ref={graphBottomRef} className="h-fit flex-1 p-4 space-y-4 overflow-auto">
                    {
                        graphMessages.map((message, index) => {
                            if (message.type === MessageTypes.Query) {
                                return (<div key={index} className="flex items-end gap-2 justify-end">
                                    <div className="rounded-lg bg-blue-500 text-white p-2">
                                        <p className="text-sm">{message.text}</p>
                                    </div>
                                </div>)
                            } else if (message.type === MessageTypes.Response) {
                                return (<div key={index} className="flex items-end gap-2">
                                    <div className="rounded-lg bg-zinc-200 p-2">
                                        <p className="text-sm">{message.text}</p>
                                    </div>
                                </div>)
                            } else {
                                return (<div key={index} className="flex items-end gap-2">
                                    <div>
                                        <Image src="/dots.gif" width={100} height={10} alt="Waiting for response" />
                                    </div>
                                </div>)
                            }
                        })
                    }
                </div>
                <div className="w-0.5 bg-gray-200" />
                <div ref={vendorBottomRef} className="h-fit flex-1 p-4 space-y-4 overflow-auto">
                    {
                        vendorMessages.map((message, index) => {
                            if (message.type === MessageTypes.Query) {
                                return (<div key={index} className="flex items-end gap-2 justify-end">
                                    <div className="rounded-lg bg-blue-500 text-white p-2">
                                        <p className="text-sm">{message.text}</p>
                                    </div>
                                </div>)
                            } else if (message.type === MessageTypes.Response) {
                                return (<div key={index} className="flex items-end gap-2">
                                    <div className="rounded-lg bg-zinc-200 p-2">
                                        <p className="text-sm">{message.text}</p>
                                    </div>
                                </div>)
                            } else {
                                return (<div key={index} className="flex items-end gap-2">
                                    <div>
                                        <Image src="/dots.gif" width={100} height={10} alt="Waiting for response" />
                                    </div>
                                </div>)
                            }
                        })
                    }
                </div>
            </main>
            <footer className="border p-4">
                {props.repo &&
                    <form className="flex flex-row gap-2" onSubmit={handleQueryClick}>
                        <Select onValueChange={onQuestionSelected}>
                            <SelectTrigger className="w-1/3">
                                <SelectValue placeholder="Suggested questions" />
                            </SelectTrigger>
                            <SelectContent>
                                {
                                    QUESTIONS.map((question, index) => {
                                        return <SelectItem key={index} value={question}>{question}</SelectItem>
                                    })
                                }
                            </SelectContent>
                        </Select>
                        <Input className="w-2/3" placeholder="Type a question..." onChange={handleQueryInputChange} />
                        <Button>Send</Button>
                    </form>
                }
            </footer>
        </>
    );
}
