import { Locator } from "@playwright/test";

export const delay = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

export const waitToBeEnabled = async (locator: Locator, timeout: number = 5000): Promise<boolean> => {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
        if (await locator.isEnabled()) {
            return true;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
    }

    return false;
};

export function findNodeByName(nodes: { name: string }[], nodeName: string): any {
    return nodes.find((node) => node.name === nodeName);
}

export function findFirstNodeWithSrc(nodes: { src?: string }[]): any {
    return nodes.find((node) => node.src !== undefined);
}

export function findNodeWithSpecificSrc(nodes: { src?: string }[], srcContent: string): any {
    return nodes.find((node) => node.src && node.src.includes(srcContent));
}