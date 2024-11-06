import { Locator } from "playwright";
import BasePage from "../../infra/ui/basePage";

export default class NavBarComponent extends BasePage {

    private get homeButton(): Locator {
        return this.page.locator("//a[p[text() = 'Home']]")
    }

    async clickOnHomeBtn(): Promise<void> {
        await this.homeButton.click()
    }
}