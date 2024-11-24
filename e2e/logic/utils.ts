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

