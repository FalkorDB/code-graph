import { Locator } from "@playwright/test";

export const delay = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

export const waitToBeEnabled = async (locator: Locator, timeout: number = 5000): Promise<void> => {
    const elementHandle = await locator.elementHandle();
    if (!elementHandle) throw new Error("Element not found");

    await locator.page().waitForFunction(
        (el) => el && !(el as HTMLElement).hasAttribute("disabled"),
        elementHandle,
        { timeout }
    );
};

export const waitForStableText = async (locator: Locator, timeout: number = 5000): Promise<string> => {
    const elementHandle = await locator.elementHandle();
    if (!elementHandle) throw new Error("Element not found");

    let previousText = "";
    let stableText = "";
    const pollingInterval = 300;
    const maxChecks = timeout / pollingInterval;

    for (let i = 0; i < maxChecks; i++) {
        stableText = await locator.textContent() ?? "";
        if (stableText === previousText && stableText.trim().length > 0) {
            return stableText;
        }
        previousText = stableText;
        await locator.page().waitForTimeout(pollingInterval);
    }

    return stableText;
};

export const waitForElementToBeVisible = async (locator:Locator,time=500,retry=5):Promise<boolean> => {

    while(retry > 0){
       if(await locator.isVisible()){
        return true
       }
       retry = retry-1
       await delay(time)
    }
    return false
}

export function findNodeByName(nodes: { name: string }[], nodeName: string): any {
    return nodes.find((node) => node.name === nodeName);
}

export function findFirstNodeWithSrc(nodes: { src?: string }[]): any {
    return nodes.find((node) => node.src !== undefined);
}

