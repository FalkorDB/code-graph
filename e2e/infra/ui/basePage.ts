import { Page } from 'playwright';

export default class BasePage {
    protected page: Page;

    constructor(page: Page) {
        this.page = page;
    }

    async initPage(){
        await this.page.waitForLoadState()
    }

    getCurrentURL() : string {
        return this.page.url();
    }

    async refreshPage(){
        await this.page.reload({ waitUntil: 'networkidle' });
    }

}