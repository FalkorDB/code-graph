import { test, expect } from '@playwright/test';
import BrowserWrapper from '../infra/ui/browserWrapper';
import CodeGraph from '../logic/POM/codeGraph';
import urls from '../config/urls.json';

test.describe(' Navbar tests', () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test("Verify clicking on falkordb logo redirects to specified URL", async () => {
    const navBar = await browser.createNewPage(CodeGraph, urls.baseUrl)
    const page = await navBar.clickOnFalkorDbLogo();
    expect(page.url()).toBe(urls.falkorDBUrl)
  })

  const navitems: { navItem: string; expectedRes: string }[] = [
    { navItem: "Home", expectedRes: urls.falkorDBUrl },
    { navItem: "Github", expectedRes: urls.falkorDbGithubUrl }
  ];  

  navitems.forEach(({navItem, expectedRes}) => {
    test(`Verify clicking on ${navItem} redirects to specified URL`, async () => {
        const navBar = await browser.createNewPage(CodeGraph, urls.baseUrl)
        const page = await navBar.getNavBarItem(navItem);
        expect(page.url()).toBe(expectedRes)
    })
  })

  test.skip("Verify that clicking the Create New Project button displays the correct dialog", async () => {
    const navBar = await browser.createNewPage(CodeGraph, urls.baseUrl)
    await navBar.clickCreateNewProjectBtn();
    expect(await navBar.isCreateNewProjectDialog()).toBe(true)
  })

  test("Validate Tip popup visibility and closure functionality", async () => {
    const navBar = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await navBar.clickOnTipBtn();
    expect(await navBar.isTipMenuVisible()).toBe(true);
    await navBar.clickOnTipMenuCloseBtn();
    expect(await navBar.isTipMenuVisible()).toBe(false);
  });
});
