import { test, expect } from '@playwright/test';
import BrowserWrapper from '../infra/ui/browserWrapper';
import NavBarComponent from '../logic/POM/navBarComponent';
import urls from '../config/urls.json';

test.describe(' Navbar tests', () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test("Verify clicking on Home redirects to specified URL", async () => {
      const navBar = await browser.createNewPage(NavBarComponent, urls.baseUrl)
      const page = await navBar.clickOnHomeBtn()
      expect(navBar.getCurrentURL()).toBe("http://localhost:3000/")
  })
});
